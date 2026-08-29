import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"src"))
from latent_space_aggregation_attacks.core.cli import inspect_config_entry
if __name__ == "__main__": inspect_config_entry()
