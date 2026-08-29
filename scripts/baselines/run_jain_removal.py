import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"src"))
from latent_space_aggregation_attacks.core.cli import guarded_entry
if __name__ == "__main__": guarded_entry("Run Jain removal baseline", "jain_removal")
