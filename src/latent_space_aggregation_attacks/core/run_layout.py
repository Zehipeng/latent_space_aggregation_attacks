from __future__ import annotations

from pathlib import Path

RUN_DIRS = (
    "protocol_snapshot", "manifests", "logs", "checkpoints_visualization_keys",
    "resume_state", "final_images_visualization_keys", "evaluation_spool",
    "evaluation", "figures",
)


def create_run_layout(root: str | Path, experiment_id: str, run_id: str) -> Path:
    run_dir = Path(root) / experiment_id / run_id
    if run_dir.exists():
        raise FileExistsError(f"Run directory is immutable: {run_dir}")
    for name in RUN_DIRS:
        (run_dir / name).mkdir(parents=True, exist_ok=False)
    return run_dir


def visualization_keys() -> tuple[str, str, str]:
    return "key_000", "key_100", "key_199"
