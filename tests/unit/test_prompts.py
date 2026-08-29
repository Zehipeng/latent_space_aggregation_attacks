from latent_space_aggregation_attacks.data.prompts import build_prompt_rows, prompt_row_order


def test_prompt_order_is_deterministic_and_unique():
    assert prompt_row_order(8_000) == prompt_row_order(8_000)
    assert len(set(prompt_row_order(8_000)[:7_500])) == 7_500


def test_prompt_banks_are_disjoint_and_nested():
    rows = build_prompt_rows(f"prompt {index}" for index in range(8_000))
    assert len(rows) == 7_500
    assert rows[0]["key_id"] == "pilot_key_000"
    assert rows[2_499]["key_id"] == "pilot_key_099"
    assert rows[2_500]["key_id"] == "key_000"
    assert rows[-1]["key_id"] == "key_199"
    assert len({row["source_row"] for row in rows}) == 7_500
