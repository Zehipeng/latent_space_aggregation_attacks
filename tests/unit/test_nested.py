import pytest
from latent_space_aggregation_attacks.data.nested import nested_prefix,key_ids
def test_nested_prefixes_are_exact():
    bank=list(range(25)); assert nested_prefix(bank,1)==[0]; assert nested_prefix(bank,5)==list(range(5)); assert nested_prefix(bank,25)==bank
def test_key_counts_are_locked():
    assert key_ids(200)[-1]=="key_199"; assert key_ids(100,pilot=True)[-1]=="pilot_key_099"
    with pytest.raises(ValueError): key_ids(10)
