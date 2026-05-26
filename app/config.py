import os
from pathlib import Path

APP_NAME = "Campus Scheduler"
DATA_DIR = Path(__file__).resolve().parent / "resources" / "data"
DB_PATH = Path(os.environ.get("CAMPUS_DB_PATH", str(DATA_DIR / "app.db")))
