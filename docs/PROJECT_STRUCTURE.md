# Project structure

The repository separates the active v1.17 execution path from historical material.

```text
latent_space_aggregation_attacks/
├─ configs/
│  ├─ current/                 # only runnable v1.17 formal/smoke configs
│  ├─ assets/                  # AutoDL inventory template
│  └─ archive/                 # v1.15/v1.16, P0, diagnostics, templates
├─ scripts/
│  ├─ run_formal.py            # single formal CLI
│  ├─ validate_batching.py     # scalar-vs-batch GPU gate
│  ├─ validate_tree_ring.py    # legacy Tree-Ring regression gate
│  ├─ operations/              # asset/manifest/inspection utilities
│  └─ archive/                 # historical P0 and inactive placeholders
├─ src/latent_space_aggregation_attacks/
│  ├─ attack.py                # fixed-budget scalar and batched optimizers
│  ├─ latent_targets.py        # forgery/removal target construction
│  ├─ formal/
│  │  ├─ prepare.py            # detector-enabled reference preparation
│  │  ├─ attack.py             # detector-free formal attack execution
│  │  ├─ evaluate.py           # independent detector/quality evaluation
│  │  ├─ orchestrator.py       # smoke, ETA, and full-run gates
│  │  ├─ worker.py             # physically isolated phase worker
│  │  └─ common.py             # formal-only shared I/O and identities
│  ├─ core/                    # generic config, hashing, resume, locks, seeds
│  ├─ watermarks/              # Tree-Ring, RingID, Gaussian Shading adapters
│  ├─ methods/baselines/       # comparison methods only
│  ├─ evaluation/              # reusable metrics and statistics
│  └─ archive/                 # historical P0 runtime
├─ tests/                      # active and archived-path regression tests
└─ docs/
   ├─ protocols/               # current v1.17 snapshot
   │  └─ archive/              # immutable prior snapshots
   └─ archive/                 # obsolete operational notes
```

## Active call chain

```text
scripts/run_formal.py
  → formal/orchestrator.py
  → formal/worker.py (new process per phase)
      → formal/prepare.py
      → formal/attack.py → attack.py
      → formal/evaluate.py
```

The `formal/__init__.py` file deliberately imports no phase module. This keeps
the attack worker from importing detector/evaluation dependencies merely by
loading the package.

## Current commands

```bash
python scripts/operations/inspect_run.py --config configs/current/formal_v1p17.yaml
python scripts/validate_tree_ring.py --help
python scripts/validate_batching.py --help
python scripts/run_formal.py --help
```

Anything under an `archive/` directory is excluded from the v1.17 formal path.
