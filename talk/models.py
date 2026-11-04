"""앱 전체가 함께 쓰는 데이터 모양. 모두 JSON으로 왕복할 수 있다."""

from dataclasses import asdict, dataclass, field
from typing import Literal

Mode = Literal["daily", "business", "verb", "pattern"]
Style = Literal["ai_story", "role_swap", "ai_secret", "ai_disagree", "user_first", "goal_roleplay"]

MODES: list[str] = ["daily", "business", "verb", "pattern"]


class _Json:
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict):
        return cls(**d)


@dataclass
class Correction(_Json):
    native: str
    why_ko: str
    extend: str | None = None


@dataclass
class Mistake(_Json):
    key: str
    original: str
    native: str
    area: str
    voice_sensitive: bool = False


@dataclass
class Message(_Json):
    role: Literal["user", "ai"]
    text: str
    ts: str
    via_voice: bool = False
    correction: Correction | None = None
    help_ko: str | None = None
    translation_ko: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "Message":
        d = dict(d)
        if d.get("correction"):
            d["correction"] = Correction.from_dict(d["correction"])
        return cls(**d)


@dataclass
class TurnResult(_Json):
    reply: str
    correction: Correction | None
    help_ko: str | None
    user_asked_question: bool
    user_led: bool
    mistakes: list[Mistake] = field(default_factory=list)
    targets_used_correctly: list[str] = field(default_factory=list)
    help_expr: str | None = None
    reply_ko: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "TurnResult":
        d = dict(d)
        if d.get("correction"):
            d["correction"] = Correction.from_dict(d["correction"])
        d["mistakes"] = [Mistake.from_dict(m) for m in d.get("mistakes", [])]
        return cls(**d)


@dataclass
class Session(_Json):
    id: str
    date: str
    mode: Mode
    topic: str
    style: Style
    started: str
    seconds: int
    messages: list[Message] = field(default_factory=list)
    turns: list[TurnResult] = field(default_factory=list)
    finished: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "Session":
        d = dict(d)
        d["messages"] = [Message.from_dict(m) for m in d.get("messages", [])]
        d["turns"] = [TurnResult.from_dict(t) for t in d.get("turns", [])]
        return cls(**d)


@dataclass
class DayPlan(_Json):
    date: str
    topics: dict[str, str]
    verb: str
    patterns: list[str]
    style: Style
    recommended: Mode
    targets: list[str] = field(default_factory=list)
