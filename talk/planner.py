"""오늘의 계획: 모드별 주제, 동사, 문형, 대화 방식, 추천 모드, 은근히 연습할 표현. 하루 동안 고정된다."""

from collections import Counter
from datetime import date, timedelta

from talk import content
from talk.models import MODES, DayPlan
from talk.store import Store

STYLES = ["ai_story", "role_swap", "ai_secret", "ai_disagree", "user_first", "goal_roleplay"]
CONTINUE = "이어서: "
MAX_TARGETS = 3


def week_id(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def _past_plans(store: Store, today: date) -> list[dict]:
    plans = []
    for p in sorted((store.root / "plans").glob("*.json")):
        if p.stem < today.isoformat():
            plan = store.load_json(f"plans/{p.name}", None)
            if isinstance(plan, dict):
                plans.append(plan)
    return plans


def _fresh_topic(mode: str, today: date, past: list[dict]) -> str:
    cutoff = (today - timedelta(days=14)).isoformat()
    recent = {p["topics"].get(mode) for p in past if p["date"] >= cutoff}
    options = content.TOPICS[mode]
    start = today.toordinal() % len(options)
    for i in range(len(options)):
        topic = options[(start + i) % len(options)]
        if topic not in recent:
            return topic
    return options[start]


def _least_used(items: list[str], used: Counter, n: int) -> list[str]:
    return sorted(items, key=lambda x: (used[x], items.index(x)))[:n]


def _targets(store: Store, today: date) -> list[str]:
    mistakes = store.load_json("memory.json", {}).get("mistakes", {})
    weekly = store.load_json(f"weekly/{week_id(today - timedelta(days=7))}.json", {})
    out = [k for k in weekly.get("next_targets", []) if not mistakes.get(k, {}).get("voice_only")]
    ranked = sorted(
        (k for k, m in mistakes.items() if not m.get("voice_only") and k not in out),
        key=lambda k: (-mistakes[k].get("count", 0), _neg_date(mistakes[k].get("last_seen", ""))),
    )
    return (out + ranked)[:MAX_TARGETS]


def _neg_date(s: str) -> tuple:
    # 최근 날짜가 먼저 오도록 정렬 키를 뒤집는다
    return tuple(-ord(c) for c in s)


def _recommended(store: Store, today: date, targets: list[str]) -> str:
    mistakes = store.load_json("memory.json", {}).get("mistakes", {})
    if any("business" in mistakes.get(k, {}).get("area", "").lower() for k in targets):
        return "business"
    since = (today - timedelta(days=7)).isoformat()
    counts = Counter(s.mode for s in store.list_sessions() if since <= s.date <= today.isoformat())
    return min(MODES, key=lambda m: (counts[m], MODES.index(m)))


def get_plan(store: Store, today: date) -> DayPlan:
    name = f"plans/{today.isoformat()}.json"
    saved = store.load_json(name, None)
    if isinstance(saved, dict):
        return DayPlan.from_dict(saved)

    past = _past_plans(store, today)
    daily = _fresh_topic("daily", today, past)
    if today.toordinal() % 4 == 0:
        prev = [s for s in store.list_sessions() if s.mode == "daily" and s.date < today.isoformat()]
        if prev:
            daily = CONTINUE + prev[-1].topic.removeprefix(CONTINUE)

    verb = _least_used(content.VERBS, Counter(p["verb"] for p in past), 1)[0]
    patterns = _least_used(content.PATTERNS, Counter(x for p in past for x in p["patterns"]), 2)
    targets = _targets(store, today)
    plan = DayPlan(
        date=today.isoformat(),
        topics={
            "daily": daily,
            "business": _fresh_topic("business", today, past),
            "verb": "오늘의 동사: " + verb,
            "pattern": ", ".join(patterns),
        },
        verb=verb,
        patterns=patterns,
        style=STYLES[today.toordinal() % 6],
        recommended=_recommended(store, today, targets),
        targets=targets,
    )
    store.save_json(name, plan.to_dict())
    return plan
