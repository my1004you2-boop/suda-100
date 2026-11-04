from datetime import date

import pytest

from talk.config import Settings
from talk.llm import FakeLLM, LLMError
from talk.memory import load_memory
from talk.models import Message, Mistake, Session, TurnResult
from talk.planner import get_plan, week_id
from talk.reports import build_weekly, finalize_session, format_score, week_metrics, week_title
from talk.startup import run_startup
from talk.store import Store

GOAL = Settings(daily_goal_min=20)
WEEK = "2026-W45"  # 11월 2일(월) ~ 8일(일)
LLM_PART = {"willpower": 7.0, "speaking": 6.4, "leadership": 5.0,
            "reasons": {"sincerity": "5일", "willpower": "복귀", "speaking": "길어짐", "understanding": "5/7",
                        "leadership": "질문 늘어남"},
            "letter": "이번 주도 수고했어요.", "weak_points": "관사", "next_plan": "관사 연습",
            "next_targets": ["very + verb", "not-a-repeated-key"]}


def sess(sid, day, seconds=1260, words="I really like it a lot", mistakes=(), asked=False, led=False):
    turns = [TurnResult("ok", None, None, asked, led, list(mistakes), [])]
    return Session(id=sid, date=day, mode="daily", topic="t", style="ai_story", started=f"{day}T09:00:00",
                   seconds=seconds, messages=[Message("ai", "Hi", "t"), Message("user", words, "t"),
                                              Message("ai", "ok", "t")], turns=turns)


VERY = Mistake("very + verb", "I very like it", "I really like it", "grammar")


def finished_week(store, days=("2026-11-02", "2026-11-03", "2026-11-05", "2026-11-06", "2026-11-07"), **kw):
    for i, d in enumerate(days):
        finalize_session(FakeLLM([LLMError("x")]), store, sess(f"s{i}", d, **kw))


def test_week_id_and_title():
    assert week_id(date(2026, 11, 4)) == "2026-W45"
    assert week_id(date(2026, 11, 8)) == "2026-W45"
    assert week_title("2026-W45") == "11월 첫째 주 평가서"
    assert week_title("2026-W46") == "11월 둘째 주 평가서"


def test_metrics_counts(tmp_path):
    store = Store(tmp_path)
    finished_week(store, mistakes=[VERY, VERY], asked=True)
    m = week_metrics(store, WEEK, GOAL)
    assert m["days_active"] == 5 and m["avg_minutes"] == 21.0 and m["goal_days"] == 5
    assert m["returned_after_gap"] == 1          # 수요일을 쉬고 목요일에 돌아옴
    assert m["avg_words_per_message"] == 6.0 and m["questions"] == 5 and m["user_led"] == 0
    assert m["repeated_keys"] == ["very + verb"]


def test_sincerity_formula(tmp_path):
    store = Store(tmp_path)
    finished_week(store)
    w = build_weekly(FakeLLM([LLM_PART]), store, WEEK, GOAL)
    assert w["scores"]["sincerity"] == 8.0


def test_understanding_none_when_no_targets(tmp_path):
    store = Store(tmp_path)
    finished_week(store)
    w = build_weekly(FakeLLM([LLM_PART]), store, WEEK, GOAL)
    assert w["scores"]["understanding"] is None
    assert format_score(None) == "—"


def test_understanding_ratio(tmp_path):
    store = Store(tmp_path)
    store.save_json("memory.json", {"topics": [], "facts": [], "mistakes": {
        k: {"original": k, "native": k, "area": "g", "count": 3, "first_seen": "2026-10-01",
            "last_seen": "2026-10-30", "last_correct": None, "voice_only": False} for k in ("a", "b")}})
    get_plan(store, date(2026, 11, 2))  # 연습 대상 a, b
    s = sess("x", "2026-11-02")
    s.turns[0].targets_used_correctly = ["a"]
    finalize_session(FakeLLM([LLMError("x")]), store, s)
    w = build_weekly(FakeLLM([LLM_PART]), store, WEEK, GOAL)
    assert w["scores"]["understanding"] == 5.0


def test_llm_scores_clamped_to_prev_week(tmp_path):
    store = Store(tmp_path)
    store.save_json("weekly/2026-W44.json", {"scores": {"willpower": 3.0, "speaking": 6.0, "leadership": 9.0}})
    finished_week(store)
    w = build_weekly(FakeLLM([dict(LLM_PART, willpower=9.0, speaking=6.4, leadership=2.0)]), store, WEEK, GOAL)
    assert w["scores"]["willpower"] == 4.5 and w["scores"]["speaking"] == 6.4 and w["scores"]["leadership"] == 7.5


def test_next_targets_only_from_repeated_and_used_by_planner(tmp_path):
    store = Store(tmp_path)
    finished_week(store, mistakes=[VERY, VERY])
    w = build_weekly(FakeLLM([LLM_PART]), store, WEEK, GOAL)
    assert w["next_targets"] == ["very + verb"]
    assert store.load_json(f"weekly/{WEEK}.json", None)["next_targets"] == ["very + verb"]
    assert get_plan(store, date(2026, 11, 9)).targets[0] == "very + verb"


def test_weekly_llm_failure_raises_and_saves_nothing(tmp_path):
    store = Store(tmp_path)
    finished_week(store)
    with pytest.raises(LLMError):
        build_weekly(FakeLLM([LLMError("busy")]), store, WEEK, GOAL)
    assert store.load_json(f"weekly/{WEEK}.json", None) is None


def test_weekly_score_format():
    assert format_score(6.44) == "6.4 / 10.0" and format_score(10) == "10.0 / 10.0"


def test_startup_finishes_unfinished_and_deletes_empty(tmp_path):
    store = Store(tmp_path)
    store.save_session(sess("talked", "2026-11-04", mistakes=[VERY]))
    empty = sess("empty", "2026-11-04")
    empty.messages, empty.turns = empty.messages[:1], []
    store.save_session(empty)
    active = sess("active", "2026-11-04")
    store.save_session(active)
    summary = {"topic_summary": "s", "new_facts": []}
    new_weekly = run_startup(FakeLLM([summary]), store, GOAL, active_id="active", today=date(2026, 11, 4))
    assert new_weekly is False
    assert store.load_session("talked").finished is True
    assert "very + verb" in load_memory(store)["mistakes"]
    assert [s.id for s in store.list_sessions()] == ["active", "talked"] or \
        sorted(s.id for s in store.list_sessions()) == ["active", "talked"]
    assert store.load_session("active").finished is False


def test_startup_builds_last_week_once(tmp_path):
    store = Store(tmp_path)
    finished_week(store)
    assert run_startup(FakeLLM([LLM_PART]), store, GOAL, None, today=date(2026, 11, 10)) is True
    assert store.load_json(f"weekly/{WEEK}.json", None) is not None
    assert run_startup(FakeLLM([]), store, GOAL, None, today=date(2026, 11, 11)) is False


def test_startup_no_weekly_without_sessions(tmp_path):
    assert run_startup(FakeLLM([]), Store(tmp_path), GOAL, None, today=date(2026, 11, 10)) is False
