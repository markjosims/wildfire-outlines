import sys
from pathlib import Path
from datetime import datetime, timezone
from src.models import Assessment

IS_WASM = sys.platform == "emscripten"
STATE_FILE = Path("/mnt/wildfire_state.json") if IS_WASM else "data/wildfire_state.json"


class DataStore:
    def __init__(self):
        self.assessment: Assessment = self._load()

    def _load(self) -> Assessment:
        datetime_str = datetime.now(timezone.utc).isoformat()
        if not STATE_FILE.exists():
            return Assessment(id=datetime_str)
        try:
            return Assessment.model_validate_json(STATE_FILE.read_text())
        except Exception:
            return Assessment(id=datetime_str)

    def save(self):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(self.assessment.model_dump_json(indent=2))
