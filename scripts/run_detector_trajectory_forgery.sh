#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -u scripts/run_detector_trajectories.py --phase run --task forgery "$@"
