from latent_space_aggregation_attacks.evaluation.eligibility import success
def test_threshold_equality_matches_protocol():
    assert success("removal","tree_ring",.01,.05,.05)[:2]==(True,True); assert success("forgery","tree_ring",.2,.05,.05)[:2]==(True,True)
