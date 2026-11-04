"""data/ 폴더의 JSON 파일 읽기·쓰기."""

import json
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path

from talk.models import Session

_write_lock = threading.Lock()


def new_session_id(now: datetime) -> str:
    return now.strftime("%Y%m%d-%H%M%S")


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)
        (self.root / "sessions").mkdir(parents=True, exist_ok=True)

    def _write(self, path: Path, obj) -> None:
        # 턴마다 저장하므로, 쓰다가 꺼져도 이전 파일이 남도록 임시 파일에 쓴 뒤 바꿔치기한다
        # 타이머(UI 스레드)와 대화(작업 스레드)가 같은 파일을 동시에 저장할 수 있어 잠금을 건다
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(obj, ensure_ascii=False, indent=1)
        with _write_lock:
            tmp = path.with_suffix(f"{path.suffix}.{uuid.uuid4().hex[:8]}.tmp")
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)

    def save_session(self, s: Session) -> None:
        self._write(self.root / "sessions" / f"{s.id}.json", s.to_dict())

    def load_session(self, id: str) -> Session:
        raw = json.loads((self.root / "sessions" / f"{id}.json").read_text(encoding="utf-8"))
        return Session.from_dict(raw)

    def delete_session(self, id: str) -> None:
        (self.root / "sessions" / f"{id}.json").unlink(missing_ok=True)

    def list_sessions(self, date: str | None = None) -> list[Session]:
        out = []
        for p in sorted((self.root / "sessions").glob("*.json")):
            try:
                s = self.load_session(p.stem)
            except (OSError, ValueError, TypeError, KeyError):
                continue
            if date is None or s.date == date:
                out.append(s)
        return sorted(out, key=lambda s: s.started)

    def unfinished_sessions(self) -> list[Session]:
        return [s for s in self.list_sessions() if not s.finished]

    def load_json(self, name: str, default):
        try:
            return json.loads((self.root / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return default

    def save_json(self, name: str, obj) -> None:
        self._write(self.root / name, obj)
