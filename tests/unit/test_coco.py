from latent_space_aggregation_attacks.data.coco import allocate_val2017_roles


def test_v19_val2017_role_allocation():
    images = [{"id": index, "file_name": f"{index:012d}.jpg", "width": 1, "height": 1} for index in range(5000)]
    first = allocate_val2017_roles(images)
    second = allocate_val2017_roles(images)
    assert first == second
    assert len(first["formal_targets"]) == 200
    assert len(first["formal_clean"]) == 5000
    assert len(first["pilot_targets"]) == 100
    assert len(first["pilot_clean"]) == 500
    assert {row["id"] for row in first["formal_targets"]}.isdisjoint({row["id"] for row in first["pilot_targets"]})
    assert len({row["id"] for row in first["formal_clean"]}) == 5000
