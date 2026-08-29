from latent_space_aggregation_attacks.core.seeds import derive_seed
def test_seed_is_stable_and_namespaced():
    assert derive_seed("generation","key_000",0)==derive_seed("generation","key_000",0)
    assert derive_seed("generation","key_000",0)!=derive_seed("watermark_key","tree_ring","key_000")
