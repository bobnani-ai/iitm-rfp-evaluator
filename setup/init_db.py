"""Initialize the project's SQLite database under data/."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from seed_db import db_path, initialize


if __name__ == "__main__":
    initialize()
    print(f"Initialized {db_path()}")
