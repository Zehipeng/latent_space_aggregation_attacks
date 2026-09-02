from __future__ import annotations
from typing import Any

from .base import Detection
from .runtime import generate_from_latents, invert_image, invert_images

class GaussianShadingAdapter:
    name = "gaussian_shading"
    def __init__(self, config: dict[str, Any]):
        if not config.get("code_revision") or config.get("bit_accuracy_threshold") is None:
            raise ValueError("Gaussian Shading code revision and bit threshold must be locked")
        if config.get("cipher") != "chacha20":
            raise ValueError("P0 Gaussian Shading locks the official ChaCha20 variant")
        self.config = config
        self.pipe = config["pipe"]
        self.threshold = float(config["bit_accuracy_threshold"])
        self.channel_copy = int(config.get("channel_copy", 1))
        self.hw_copy = int(config.get("hw_copy", 8))
        self.generation_steps = int(config.get("generation_steps", 50))
        self.inversion_steps = int(config.get("inversion_steps", 50))

    def create_key(self, key_record: dict[str, Any]) -> Any:
        import hashlib
        import numpy as np
        import torch
        from Crypto.Cipher import ChaCha20

        seed = int(key_record["watermark_seed"])
        generator = torch.Generator(device="cpu").manual_seed(seed)
        message = torch.randint(
            0, 2,
            (1, 4 // self.channel_copy, 64 // self.hw_copy, 64 // self.hw_copy),
            generator=generator,
            dtype=torch.uint8,
        )
        spread = message.repeat(1, self.channel_copy, self.hw_copy, self.hw_copy)
        material = hashlib.sha512(f"{seed}|gaussian_shading_chacha20".encode("utf-8")).digest()
        cipher_key, nonce = material[:32], material[32:44]
        cipher = ChaCha20.new(key=cipher_key, nonce=nonce)
        encrypted_bytes = cipher.encrypt(np.packbits(spread.flatten().numpy()).tobytes())
        encrypted = np.unpackbits(np.frombuffer(encrypted_bytes, dtype=np.uint8))[: 4 * 64 * 64]
        encrypted_bits = torch.from_numpy(encrypted.copy()).reshape(1, 4, 64, 64).to(torch.uint8)
        return {
            "cipher_key": cipher_key, "nonce": nonce, "message": message.to(self.pipe.device),
            "encrypted_bits": encrypted_bits, "seed": seed,
        }

    def generate(self, prompt: str, key: Any, seed: int) -> Any:
        import torch
        from scipy.special import ndtri
        encrypted = key["encrypted_bits"]
        generator = torch.Generator(device="cpu").manual_seed(int(seed))
        uniform = torch.rand((1, 4, 64, 64), generator=generator, dtype=torch.float64)
        probabilities = ((uniform + encrypted.to(torch.float64)) / 2.0).clamp(1e-12, 1.0 - 1e-12)
        latents = torch.from_numpy(ndtri(probabilities.numpy())).to(self.pipe.device, dtype=torch.float32)
        return generate_from_latents(self.pipe, prompt, latents, steps=self.generation_steps)

    def _recover_message(self, inverted: Any, key: Any) -> Any:
        import numpy as np
        import torch
        from Crypto.Cipher import ChaCha20
        reversed_bits = (inverted > 0).to(torch.uint8)
        cipher = ChaCha20.new(key=key["cipher_key"], nonce=key["nonce"])
        decrypted_bytes = cipher.decrypt(np.packbits(reversed_bits.flatten().cpu().numpy()).tobytes())
        decrypted_array = np.unpackbits(np.frombuffer(decrypted_bytes, dtype=np.uint8))[: 4 * 64 * 64]
        decrypted = torch.from_numpy(decrypted_array.copy()).reshape(1, 4, 64, 64).to(self.pipe.device, dtype=torch.uint8)
        channel_stride = 4 // self.channel_copy
        hw_stride = 64 // self.hw_copy
        split_channel = torch.cat(torch.split(decrypted, channel_stride, dim=1), dim=0)
        split_height = torch.cat(torch.split(split_channel, hw_stride, dim=2), dim=0)
        split_width = torch.cat(torch.split(split_height, hw_stride, dim=3), dim=0)
        vote = split_width.sum(dim=0)
        copy_count = self.channel_copy * self.hw_copy * self.hw_copy
        return (vote > copy_count // 2).to(torch.uint8)

    def invert(self, image: Any) -> Any:
        return invert_image(self.pipe, image, steps=self.inversion_steps)

    def invert_many(self, images: list[Any]) -> Any:
        return invert_images(self.pipe, images, steps=self.inversion_steps)

    def detect_inverted(self, inverted: Any, key: Any) -> Detection:
        recovered = self._recover_message(inverted, key)
        score = float((recovered == key["message"][0]).float().mean().item())
        return Detection(score=score, accepted=score >= self.threshold, score_name="bit_accuracy")

    def detect(self, image: Any, key: Any) -> Detection:
        return self.detect_inverted(self.invert(image), key)
