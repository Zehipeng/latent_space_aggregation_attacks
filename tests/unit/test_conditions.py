from latent_space_aggregation_attacks.core.conditions import expected_output_counts,formal_condition_registry,validate_registry_scale
def test_registry_is_deduplicated_and_counts_are_locked():
    conditions=formal_condition_registry(); ids=[c.id for c in conditions]; assert len(ids)==len(set(ids)); validate_registry_scale(conditions)
    assert len(conditions)*200==expected_output_counts()["formal_unique_outputs"]
    assert sum(c.method in {"jain","proposed"} for c in conditions)*200==expected_output_counts()["iterative_outputs"]
    assert expected_output_counts()["p0_online_units"]==0
    assert expected_output_counts()["p0_confirmation_units"]==0
    beta_values = sorted({c.beta for c in conditions if c.task == "removal" and c.method == "proposed" and c.N == 5 and c.lambda_pixel == 10000.0})
    assert beta_values == [1.0, 1.5, 2.0]
