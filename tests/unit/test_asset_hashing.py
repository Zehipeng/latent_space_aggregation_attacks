from latent_space_aggregation_attacks.core.hashing import sha256_tree

def test_tree_hash_is_order_stable_and_tracks_content(tmp_path):
    (tmp_path/"b").write_bytes(b"2"); (tmp_path/"a").write_bytes(b"1")
    first=sha256_tree(tmp_path); second=sha256_tree(tmp_path)
    assert first==second and first[1:]==(2,2)
    (tmp_path/"a").write_bytes(b"changed")
    assert sha256_tree(tmp_path)[0]!=first[0]


def test_tree_hash_ignores_vcs_and_runtime_cache_mutations(tmp_path):
    (tmp_path / "source.py").write_text("stable", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "index").write_bytes(b"first")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "source.pyc").write_bytes(b"first")
    first = sha256_tree(tmp_path)
    (tmp_path / ".git" / "index").write_bytes(b"second")
    (tmp_path / "__pycache__" / "source.pyc").write_bytes(b"second")
    assert sha256_tree(tmp_path) == first
