import pytest
from latent_space_aggregation_attacks import PROTOCOL_VERSION
from latent_space_aggregation_attacks.core.resume import ResumeState,save_resume_state,load_resume_state
def test_resume_checksum_and_identity(tmp_path):
    path=tmp_path/"state.pkl"; state=ResumeState("unit",50,"tensor",[],{},{},"input","config",PROTOCOL_VERSION,"abc"); save_resume_state(path,state)
    assert load_resume_state(path,expected_unit_id="unit",input_hash="input",resolved_config_hash="config",protocol_version=PROTOCOL_VERSION,git_sha="abc").step==50
    path.write_bytes(path.read_bytes()+b"corrupt")
    with pytest.raises(ValueError,match="checksum"): load_resume_state(path,expected_unit_id="unit",input_hash="input",resolved_config_hash="config",protocol_version=PROTOCOL_VERSION,git_sha="abc")
