from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("DATABASE_PATH", ROOT / "database" / "faculty.sqlite"))


def settings() -> dict:
    data = json.loads((ROOT / "config" / "settings.json").read_text(encoding="utf-8"))
    data["openai_api_key"] = os.getenv("OPENAI_API_KEY", "")
    data["openai_model"] = os.getenv("OPENAI_MODEL", data.get("openai_model", "gpt-5-mini"))
    data["search_api_key"] = os.getenv("SEARCH_API_KEY", "")
    data["search_endpoint"] = os.getenv("SEARCH_ENDPOINT", "")
    return data
