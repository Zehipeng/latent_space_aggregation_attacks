import pytest
torch=pytest.importorskip("torch")
from latent_space_aggregation_attacks.methods.proposed.targets import fp32_mean,removal_target
from latent_space_aggregation_attacks.methods.baselines.jain import jain_forgery_target,jain_removal_mean_image
from latent_space_aggregation_attacks.methods.baselines.simple_averaging import estimate_pixel_direction,apply_pixel_direction
def test_formal_targets():
    refs=torch.tensor([1,3,8],dtype=torch.float16).reshape(3,1,1,1); assert fp32_mean(refs).item()==4; assert jain_forgery_target(refs).item()==1
    assert removal_target(torch.tensor([[[5.]]]),refs,torch.ones_like(refs),1.0).item()==2
def test_simple_averaging():
    direction=estimate_pixel_direction(torch.tensor([.6,.8]).reshape(2,1,1,1),torch.tensor([.2,.4]).reshape(2,1,1,1)); assert direction.item()==pytest.approx(.4)
    assert apply_pixel_direction(torch.tensor([[[.8]]]),direction,"forgery").item()==1
    image=torch.tensor([0.,1.]).reshape(1,1,1,2); assert torch.equal(jain_removal_mean_image(image),torch.full_like(image,.5))
