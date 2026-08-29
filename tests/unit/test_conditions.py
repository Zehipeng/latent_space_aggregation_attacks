from latent_space_aggregation_attacks.core.conditions import expected_output_counts,formal_condition_registry,validate_registry_scale
def test_registry_is_deduplicated_and_counts_are_locked():
    conditions=formal_condition_registry(); ids=[c.id for c in conditions]; assert len(ids)==len(set(ids)); validate_registry_scale(conditions)
    assert len(conditions)*200==expected_output_counts()["formal_unique_outputs"]
    assert sum(c.method in {"jain","proposed"} for c in conditions)*200==expected_output_counts()["iterative_outputs"]
