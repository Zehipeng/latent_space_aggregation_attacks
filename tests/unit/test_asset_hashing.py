from latent_space_aggregation_attacks.core.hashing import sha256_tree

def test_tree_hash_is_order_stable_and_tracks_content(tmp_path):
    (tmp_path/"b").write_bytes(b"2"); (tmp_path/"a").write_bytes(b"1")
    first=sha256_tree(tmp_path); second=sha256_tree(tmp_path)
    assert first==second and first[1:]==(2,2)
    (tmp_path/"a").write_bytes(b"changed")
    assert sha256_tree(tmp_path)[0]!=first[0]
