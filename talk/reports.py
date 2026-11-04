"""일일 리포트와 주간 평가서."""

import json
import math
import threading
from collections import Counter
from datetime import date, timedelta

from talk.config import Settings
from talk.llm import LLM
from talk.memory import SessionOutcome, finish_session
from talk.models import Session
from talk.planner import week_id
from talk.store import Store


# 앱 시작 정리와 '대화 끝내기'가 동시에 memory.json·daily를 고치지 않게 한다
_finalize_lock = threading.Lock()


def _empty_daily(date: str) -> dict:
    return {"date": date, "sessions": [], "seconds": 0, "user_messages": 0,
            "learned": [], "repeated": [], "now_correct": []}


def load_daily(store: Store, date: str) -> dict | None:
    return store.load_json(f"daily/{date}.json", None)


def daily_dates(store: Store) -> list[str]:
    return sorted((p.stem for p in (store.root / "daily").glob("*.json")), reverse=True)


def update_daily(store: Store, session: Session, outcome: SessionOutcome) -> dict:
    report = load_daily(store, session.date) or _empty_daily(session.date)
    if any(s["id"] == session.id for s in report["sessions"]):
        return report
    report["sessions"].append({"id": session.id, "mode": session.mode, "topic": session.topic,
                               "seconds": session.seconds})
    report["seconds"] += session.seconds
    report["user_messages"] += sum(1 for m in session.messages if m.role == "user")
    report["learned"] += outcome.learned
    for field in ("repeated", "now_correct"):
        by_key = {r["key"]: r for r in report[field]}
        by_key.update({r["key"]: r for r in getattr(outcome, field)})
        report[field] = list(by_key.values())
    store.save_json(f"daily/{session.date}.json", report)
    return report


def finalize_session(llm: LLM, store: Store, session: Session) -> dict:
    """대화 마무리: 기억 정리 → 일일 리포트 → 마지막에 finished 표시. 중간에 꺼져도 다시 부르면 된다."""
    with _finalize_lock:
        store.save_session(session)
        report = update_daily(store, session, finish_session(llm, store, session))
        session.finished = True
        store.save_session(session)
        return report


def goal_progress(store: Store, date: str, settings: Settings, live_seconds: int = 0) -> tuple[int, int]:
    report = load_daily(store, date)
    done = (report["seconds"] if report else 0) + live_seconds
    return done // 60, settings.daily_goal_min


# ----- 주간 평가서 -----

ORDINALS = ["첫째", "둘째", "셋째", "넷째", "다섯째"]
CLAMP = 1.5
LLM_SCORES = ("willpower", "speaking", "leadership")
SCORE_KEYS = ("sincerity", "willpower", "speaking", "understanding", "leadership")

_NUM = {"type": "NUMBER"}
_STR = {"type": "STRING"}
WEEKLY_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "willpower": _NUM, "speaking": _NUM, "leadership": _NUM,
        "reasons": {"type": "OBJECT", "properties": {k: _STR for k in SCORE_KEYS}},
        "letter": _STR, "weak_points": _STR, "next_plan": _STR,
        "next_targets": {"type": "ARRAY", "items": _STR},
    },
    "required": ["willpower", "speaking", "leadership", "reasons", "letter", "weak_points", "next_plan",
                 "next_targets"],
}

WEEKLY_PROMPT = (
    "You are a warm English-conversation coach writing a weekly evaluation for a Korean learner. Write in Korean. "
    "letter: 4-6 sentences, praise first, warm and encouraging, no guilt about missed days. "
    "Score willpower (came back after gaps, met the daily goal), speaking (sentence length, variety, naturalness, "
    "compared to last week) and leadership (asking questions and starting topics, compared to last week) from 0 to "
    "10 with one decimal. reasons: one short Korean line per item (sincerity, willpower, speaking, understanding, "
    "leadership). weak_points: what to work on, in Korean. next_plan: how next week's conversations will help, in "
    "Korean. next_targets: up to 3 keys chosen ONLY from metrics.repeated_keys.\n\nData: "
)


def _week_days(week: str) -> list[date]:
    y, w = week.split("-W")
    return [date.fromisocalendar(int(y), int(w), d) for d in range(1, 8)]


def _prev_week(week: str) -> str:
    return week_id(_week_days(week)[0] - timedelta(days=7))


def week_title(week: str) -> str:
    monday = _week_days(week)[0]
    return f"{monday.month}월 {ORDINALS[(monday.day - 1) // 7]} 주 평가서"


def week_label(week: str, today: date | None = None) -> str:
    """메뉴에 보이는 이름. 올해가 아니면 연도를 붙여 해마다 겹치지 않게 한다."""
    year = _week_days(week)[0].year
    prefix = "" if year == (today or date.today()).year else f"{year}년 "
    return prefix + week_title(week)


def format_score(x) -> str:
    return "—" if x is None else f"{float(x):.1f} / 10.0"


def week_sessions(store: Store, week: str) -> list[Session]:
    days = {d.isoformat() for d in _week_days(week)}
    return [s for s in store.list_sessions() if s.date in days and s.finished]


def _talk_stats(sessions: list[Session]) -> tuple[float, int, int]:
    users = [m for s in sessions for m in s.messages if m.role == "user"]
    words = round(sum(len(m.text.split()) for m in users) / len(users), 1) if users else 0.0
    turns = [t for s in sessions for t in s.turns]
    return words, sum(t.user_asked_question for t in turns), sum(t.user_led for t in turns)


def week_metrics(store: Store, week: str, settings: Settings) -> dict:
    days = _week_days(week)
    dailies = [load_daily(store, d.isoformat()) for d in days]
    active_days = [d for d, r in zip(days, dailies) if r and r["seconds"] > 0]
    total = sum(r["seconds"] for r in dailies if r)
    every_active = {s.date for s in store.list_sessions() if s.finished}
    returned = 0
    for d in active_days:
        before = (d - timedelta(days=1)).isoformat()
        if before not in every_active and any(a < before for a in every_active):
            returned += 1  # 쉰 날 다음 날 돌아옴

    sessions = week_sessions(store, week)
    words, questions, led = _talk_stats(sessions)
    prev_words, prev_questions, prev_led = _talk_stats(week_sessions(store, _prev_week(week)))

    targets: list[str] = []
    for d in days:
        plan = store.load_json(f"plans/{d.isoformat()}.json", None) or {}
        targets += [t for t in plan.get("targets", []) if t not in targets]
    fixed_keys = {item["key"] for r in dailies if r for item in r["now_correct"]}
    counts = Counter(m.key for s in sessions for t in s.turns for m in t.mistakes if not m.voice_sensitive)

    return {
        "days_active": len(active_days),
        "avg_minutes": round(total / 60 / len(active_days), 1) if active_days else 0.0,
        "goal_days": sum(1 for r in dailies if r and r["seconds"] >= settings.daily_goal_min * 60),
        "returned_after_gap": returned,
        "avg_words_per_message": words, "prev_avg_words": prev_words,
        "targets": targets, "fixed": [t for t in targets if t in fixed_keys],
        "questions": questions, "user_led": led, "prev_questions": prev_questions, "prev_user_led": prev_led,
        "repeated_keys": [k for k, n in counts.most_common() if n >= 2],
    }


def build_weekly(llm: LLM, store: Store, week: str, settings: Settings) -> dict:
    m = week_metrics(store, week, settings)
    goal = settings.daily_goal_min or 1
    sincerity = round(min(10, m["days_active"] / 7 * 7 + min(m["avg_minutes"] / goal, 1) * 3), 1)
    understanding = round(len(m["fixed"]) / len(m["targets"]) * 10, 1) if m["targets"] else None
    prev = store.load_json(f"weekly/{_prev_week(week)}.json", None) or {}
    dailies = [r for r in (load_daily(store, d.isoformat()) for d in _week_days(week)) if r]
    data = json.dumps({"metrics": m, "sincerity": sincerity, "understanding": understanding,
                       "daily_reports": dailies, "last_week_scores": prev.get("scores")}, ensure_ascii=False)
    out = llm.generate_json(WEEKLY_PROMPT + data, [], WEEKLY_SCHEMA)

    scores = {"sincerity": sincerity, "understanding": understanding}
    for k in LLM_SCORES:
        last = (prev.get("scores") or {}).get(k)
        try:
            v = float(out.get(k))
            if not math.isfinite(v):
                raise ValueError
        except (TypeError, ValueError):
            scores[k] = last  # 이상한 점수는 "0.0"으로 보이지 않게 지난주 점수(없으면 "—")로 둔다
            continue
        v = max(0.0, min(10.0, v))
        if last is not None:
            v = max(last - CLAMP, min(last + CLAMP, v))  # 같은 실력이면 점수가 크게 흔들리지 않게
        scores[k] = round(v, 1)
    picked = [k for k in out.get("next_targets") or [] if k in m["repeated_keys"]][:3]
    level = current_level(store, before=week)
    weekly = {
        "week": week, "metrics": m, "scores": scores, "reasons": out.get("reasons") or {},
        "letter": str(out.get("letter") or ""), "weak_points": str(out.get("weak_points") or ""),
        "next_plan": str(out.get("next_plan") or ""), "next_targets": picked or m["repeated_keys"][:3],
        "level_before": level, "level_after": next_level(level, m["days_active"]),
    }
    store.save_json(f"weekly/{week}.json", weekly)
    return weekly


def weekly_ids(store: Store) -> list[str]:
    return sorted((p.stem for p in (store.root / "weekly").glob("*.json")), reverse=True)


# ----- 대화 수준 -----

START_LEVEL = 1.0
MAX_LEVEL = 10.0
FIRST_STEP = 0.6   # 처음엔 티 나게
MIN_STEP = 0.15    # 높아지면 천천히
FULL_STEP_DAYS = 3


def next_level(level: float, days_active: int) -> float:
    """한 주가 지날 때 다음 수준. 낮을수록 많이, 높을수록 조금 오른다. 거의 쉬었으면 덜 오른다."""
    step = max(MIN_STEP, FIRST_STEP * (MAX_LEVEL - level) / (MAX_LEVEL - START_LEVEL))
    if days_active == 0:
        step = 0.0
    elif days_active < FULL_STEP_DAYS:
        step /= 2
    return round(min(MAX_LEVEL, level + step), 1)


def current_level(store: Store, before: str | None = None) -> float:
    """가장 최근 주간 평가서가 정한 수준. before를 주면 그 주보다 앞선 평가서만 본다."""
    for week in weekly_ids(store):
        if before is not None and week >= before:
            continue
        data = store.load_json(f"weekly/{week}.json", None) or {}
        if isinstance(data.get("level_after"), (int, float)):
            return float(data["level_after"])
    return START_LEVEL
