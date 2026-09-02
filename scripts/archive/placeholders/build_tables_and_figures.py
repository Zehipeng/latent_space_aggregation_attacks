import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"src"))
from latent_space_aggregation_attacks.core.cli import guarded_entry
if __name__ == "__main__": guarded_entry("Build protocol-locked tables and figures", "build_tables_and_figures")
