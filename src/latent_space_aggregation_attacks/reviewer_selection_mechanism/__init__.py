"""Reference-selection bias and shared mechanism experiment."""

PROTOCOL_VERSION = "reviewer_selection_mechanism_v1.0"
MODEL_ORDER = (
    "same_model_sd14_target_sd14_vae_proxy",
    "cross_model_sd2_target_sd14_vae_proxy",
)
WATERMARK_ORDER = ("tree_ring", "ringid", "gaussian_shading")
TASK_ORDER = ("forgery", "removal")
