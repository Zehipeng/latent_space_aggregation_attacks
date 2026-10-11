from __future__ import annotations

import argparse
from pathlib import Path

from ..models.asset_lock import load_and_verify_assets, require_offline, validate_formal_assets
from .common import identity, keys
from .config import load_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("prepare", "attack", "evaluate"), required=True)
    parser.add_argument("--config", required=True); parser.add_argument("--assets-lock", required=True)
    parser.add_argument("--run-dir", required=True); parser.add_argument("--run-id", required=True)
    parser.add_argument("--project-root", required=True); parser.add_argument("--offline", action="store_true")
    args = parser.parse_args(); require_offline(args.offline)
    config = load_config(args.config); lock = load_and_verify_assets(args.assets_lock); validate_formal_assets(lock)
    root, project = Path(args.run_dir), Path(args.project_root); key_ids = keys(int(config["key_count"]))
    if args.phase == "prepare":
        from .prepare import prepare
        result = prepare(config, lock, root, args.run_id, key_ids, project)
    elif args.phase == "attack":
        from .attack import attack
        result = attack(config, lock, root, args.run_id, key_ids, identity(config, lock, project, args.run_id, key_ids)["git_sha"])
    else:
        from .evaluate import evaluate
        result = evaluate(config, lock, root, args.run_id, key_ids, config["run_mode"] == "smoke")
    print(result, flush=True)


if __name__ == "__main__": main()
