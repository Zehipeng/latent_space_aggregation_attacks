"""Additional one-watermarked-reference/five-clean-reference experiment."""

PROTOCOL_VERSION = "limited_access_v1.0"
MODEL_SETTING = "cross_model_sd2_target_sd14_vae_proxy"
WATERMARK_ORDER = ("tree_ring", "ringid", "gaussian_shading")
TASK_ORDER = ("removal", "forgery")
