from dataclasses import dataclass

@dataclass(frozen=True)
class SmokeSignature:
    protocol_version:str; resolved_config_hash:str; git_sha:str; assets_lock_hash:str; sample_manifest_hash:str

def require_full_run_gate(signature:SmokeSignature,passed_signature:SmokeSignature|None,smoke_passed:bool)->None:
    if not smoke_passed or passed_signature!=signature:
        raise RuntimeError("Matching 2-key smoke has not passed; full run is prohibited")
