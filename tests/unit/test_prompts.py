from latent_space_aggregation_attacks.data.prompts import build_prompt_rows, prompt_row_order


def test_prompt_order_is_deterministic_and_unique():
    assert prompt_row_order(20_000) == prompt_row_order(20_000)
    assert len(set(prompt_row_order(20_000)[:19_200])) == 19_200


def test_prompt_banks_are_disjoint_and_nested():
    rows = build_prompt_rows(f"prompt {index}" for index in range(20_000))
    assert len(rows) == 19_200
    assert rows[0]["key_id"] == "pilot_key_000"
    assert rows[6_399]["key_id"] == "pilot_key_099"
    assert rows[6_400]["key_id"] == "key_000"
    assert rows[-1]["key_id"] == "key_199"
    assert len({row["source_row"] for row in rows}) == 19_200
