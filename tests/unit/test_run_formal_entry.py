from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_run_formal_resolves_git_project_root() -> None:
    entry = ROOT / "scripts/run_formal.py"
    spec = importlib.util.spec_from_file_location("formal_entry_for_test", entry)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.PROJECT_ROOT == ROOT
    assert (module.PROJECT_ROOT / ".git").exists()
