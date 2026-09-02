import pytest
torch=pytest.importorskip("torch")
from latent_space_aggregation_attacks.latent_targets import fp32_mean,removal_target
from latent_space_aggregation_attacks.methods.baselines.jain import jain_forgery_target,jain_removal_mean_image
from latent_space_aggregation_attacks.methods.baselines.simple_averaging import estimate_pixel_direction,apply_pixel_direction
from latent_space_aggregation_attacks.attack import optimize_fixed_budget,optimize_fixed_budget_batch
from latent_space_aggregation_attacks.watermarks.runtime import image_to_tensor
def test_formal_targets():
    refs=torch.tensor([1,3,8],dtype=torch.float16).reshape(3,1,1,1); assert fp32_mean(refs).item()==4; assert jain_forgery_target(refs).item()==1
    assert fp32_mean(refs).shape==(1,1,1,1)
    assert removal_target(torch.tensor([[[5.]]]),refs,torch.ones_like(refs),1.0).item()==2
    assert removal_target(torch.tensor([[[5.]]]),refs,torch.ones_like(refs),1.5).item()==pytest.approx(.5)
    with pytest.raises(ValueError, match="beta must be one of"):
        removal_target(torch.tensor([[[5.]]]),refs,torch.ones_like(refs),1.25)
def test_simple_averaging():
    direction=estimate_pixel_direction(torch.tensor([.6,.8]).reshape(2,1,1,1),torch.tensor([.2,.4]).reshape(2,1,1,1)); assert direction.item()==pytest.approx(.4)
    assert apply_pixel_direction(torch.tensor([[[.8]]]),direction,"forgery").item()==1
    image=torch.tensor([0.,1.]).reshape(1,1,1,2); assert torch.equal(jain_removal_mean_image(image),torch.full_like(image,.5))


def test_optimizer_resume_uses_saved_current_image():
    class Distribution:
        def __init__(self, value): self.value = value
        def mode(self): return self.value
    class Encoded:
        def __init__(self, value): self.latent_dist = Distribution(value)
    class VAE(torch.nn.Module):
        def __init__(self):
            super().__init__(); self.anchor=torch.nn.Parameter(torch.zeros(())); self.config=type("Config",(),{"scaling_factor":1.0})()
        def encode(self, value): return Encoded(value + self.anchor * 0)
    vae=VAE(); original=torch.zeros(1,1,1,1); resumed=torch.full_like(original,.5)
    result=optimize_fixed_budget(original,resumed,vae,lambda_pixel=0,learning_rate=.02,final_step=2,start_step=1,current_image=resumed,original_image=original)
    assert result.final_step==2
    assert result.image.item()==pytest.approx(.5)


def test_optimizer_matches_reference_gradient_descent_update():
    class Distribution:
        def __init__(self, value): self.value = value
        def mode(self): return self.value
    class Encoded:
        def __init__(self, value): self.latent_dist = Distribution(value)
    class VAE(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.anchor = torch.nn.Parameter(torch.zeros(()))
            self.config = type("Config", (), {"scaling_factor": 1.0})()
        def encode(self, value): return Encoded(value.square() + self.anchor * 0)

    vae = VAE()
    original = torch.tensor([[[[-0.8, -0.2], [0.3, 0.9]]]])
    target = torch.tensor([[[[0.1, 0.4], [0.2, 0.7]]]])
    expected = original.clone()
    for _ in range(3):
        expected.requires_grad_(True)
        encoded = vae.encode(expected).latent_dist.mode()
        loss = torch.nn.functional.mse_loss(encoded, target)
        loss = loss + 2.0 * torch.nn.functional.mse_loss(expected, original)
        gradient = torch.autograd.grad(loss, expected, only_inputs=True)[0]
        expected = (expected - 0.02 * gradient).clamp(-1.0, 1.0).detach()

    actual = optimize_fixed_budget(
        original, target, vae, lambda_pixel=2.0,
        learning_rate=0.02, final_step=3,
    )
    torch.testing.assert_close(actual.image, expected, rtol=0, atol=0)


def test_batched_optimizer_matches_independent_scalar_updates():
    class Distribution:
        def __init__(self, value): self.value = value
        def mode(self): return self.value
    class Encoded:
        def __init__(self, value): self.latent_dist = Distribution(value)
    class VAE(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.anchor = torch.nn.Parameter(torch.tensor(0.0))
            self.config = type("Config", (), {"scaling_factor": 1.0})()
        def encode(self, value): return Encoded(value * 1.7 + self.anchor * 0)

    vae = VAE()
    images = torch.tensor([[[[0.1, -0.2]]], [[[0.3, 0.4]]]])
    targets = torch.tensor([[[[0.8, -0.5]]], [[[-0.2, 0.7]]]])
    lambdas = [1.0, 3.0]
    expected = torch.cat([
        optimize_fixed_budget(
            images[index:index + 1], targets[index:index + 1], vae,
            lambda_pixel=lambdas[index], learning_rate=0.02, final_step=3,
        ).image
        for index in range(2)
    ])
    actual = optimize_fixed_budget_batch(
        images, targets, vae, lambda_pixels=lambdas,
        learning_rate=0.02, final_step=3,
    )
    torch.testing.assert_close(actual.images, expected, rtol=0, atol=1e-7)
    assert [history[-1]["step"] for history in actual.loss_histories] == [3, 3]


def test_optimizers_accept_targets_created_in_inference_mode():
    class Distribution:
        def __init__(self, value): self.value = value
        def mode(self): return self.value
    class Encoded:
        def __init__(self, value): self.latent_dist = Distribution(value)
    class VAE(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.anchor = torch.nn.Parameter(torch.tensor(0.0))
            self.config = type("Config", (), {"scaling_factor": 1.0})()
        def encode(self, value): return Encoded(value * 1.7 + self.anchor * 0)

    vae = VAE()
    images = torch.tensor([[[[0.1, -0.2]]], [[[0.3, 0.4]]]])
    with torch.inference_mode():
        targets = vae.encode(images.roll(1, 0)).latent_dist.mode()

    scalar = optimize_fixed_budget(
        images[0:1], targets[0:1], vae,
        lambda_pixel=1.0, learning_rate=0.02, final_step=1,
    )
    batched = optimize_fixed_budget_batch(
        images, targets, vae, lambda_pixels=[1.0, 1.0],
        learning_rate=0.02, final_step=1,
    )

    assert scalar.final_step == 1
    assert batched.final_step == 1


def test_pil_preprocessing_matches_short_side_resize_and_center_crop():
    from PIL import Image
    import numpy as np

    source = Image.new("RGB", (8, 4), "black")
    pixels = np.asarray(source).copy()
    pixels[:, :2] = (255, 0, 0)
    pixels[:, 6:] = (0, 0, 255)
    source = Image.fromarray(pixels)
    tensor = image_to_tensor(source, size=4, device="cpu", dtype=torch.float32)
    # Short-side resize leaves width 8 and center-crops columns 2..5, so the
    # colored edge bands must not survive.  Direct square stretching would.
    assert tensor.shape == (1, 3, 4, 4)
    assert torch.equal(tensor, torch.full_like(tensor, -1.0))
