"""앱 이름, 경로와 사용자 설정(settings.json)."""

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Literal

APP_NAME = "수다백단"
APP_NAME_EN = "Suda 100"

APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
SETTINGS_PATH = APP_DIR / "settings.json"


@dataclass
class Settings:
    api_key: str = ""
    model: str = "gemini-2.5-flash"
    daily_goal_min: int = 20
    voice: str = "en-US-AvaMultilingualNeural"
    speed: Literal["slow", "normal", "native"] = "normal"
    auto_read: bool = False
    mic_device: int | None = None
    whisper_model: str = "base.en"


def load_settings(path: Path = SETTINGS_PATH) -> Settings:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    if not isinstance(raw, dict):
        return Settings()
    known = {f.name for f in fields(Settings)}
    return Settings(**{k: v for k, v in raw.items() if k in known})


def save_settings(s: Settings, path: Path = SETTINGS_PATH) -> None:
    path.write_text(json.dumps(asdict(s), ensure_ascii=False, indent=2), encoding="utf-8")
