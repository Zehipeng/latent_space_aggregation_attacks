from latent_space_aggregation_attacks.core.conditions import conditions_for_task,expected_output_counts,formal_condition_registry,validate_registry_scale
def test_registry_is_deduplicated_and_counts_are_locked():
    conditions=formal_condition_registry(); ids=[c.id for c in conditions]; assert len(ids)==len(set(ids)); validate_registry_scale(conditions)
    assert len(conditions)*200==expected_output_counts()["formal_unique_outputs"]
    assert sum(c.method in {"jain","proposed"} for c in conditions)*200==expected_output_counts()["iterative_outputs"]
    assert expected_output_counts()["p0_online_units"]==0
    assert expected_output_counts()["p0_confirmation_units"]==0
    beta_values = sorted({c.beta for c in conditions if c.task == "removal" and c.method == "proposed" and c.N == 5 and c.lambda_pixel == 10000.0})
    assert beta_values == [1.0, 1.5, 2.0]
    main_removal = [c for c in conditions if c.experiment == "E2" and c.method == "proposed"]
    assert main_removal and {c.beta for c in main_removal} == {1.5}
    lambda_removal = [c for c in conditions if c.experiment == "E3" and c.task == "removal" and c.method == "proposed"]
    assert lambda_removal and {c.beta for c in lambda_removal} == {1.5}
    n_removal = [c for c in conditions if c.experiment == "E4" and c.task == "removal" and c.method == "proposed"]
    assert n_removal and {c.beta for c in n_removal} == {1.5}

def test_forgery_registry_and_smoke_counts_are_config_aware():
    conditions = conditions_for_task("forgery")
    assert len(conditions) == 66
    assert sum(condition.method in {"jain", "proposed"} for condition in conditions) == 48
    assert expected_output_counts(task="forgery") == {
        "formal_unique_outputs": 13200,
        "iterative_outputs": 9600,
        "p0_online_units": 0,
        "p0_confirmation_units": 0,
    }
    assert expected_output_counts(key_count=2)["formal_unique_outputs"] == 348
