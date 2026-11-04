from talk.llm import FakeLLM
from talk.prompts import build_system_prompt
from talk.reports import build_weekly, current_level, next_level
from talk.store import Store
from tests.test_conversation import MEMORY, PLAN
from tests.test_ui_daily import all_text
from tests.test_weekly import GOAL, LLM_PART, WEEK, finished_week


def test_level_rises_noticeably_early_then_slowly():
    assert next_level(1.0, days_active=5) == 1.6
    early = next_level(2.0, 5) - 2.0
    late = next_level(8.0, 5) - 8.0
    assert early > late and late >= 0.15 - 1e-9
    assert next_level(9.95, 7) == 10.0


def test_half_step_when_few_days():
    assert next_level(1.0, days_active=2) == 1.3
    assert next_level(1.0, days_active=0) == 1.0


def test_weekly_saves_level_and_current_level_follows(tmp_path):
    store = Store(tmp_path)
    assert current_level(store) == 1.0
    finished_week(store)  # 5일
    w = build_weekly(FakeLLM([LLM_PART]), store, WEEK, GOAL)
    assert (w["level_before"], w["level_after"]) == (1.0, 1.6)
    assert current_level(store) == 1.6


def test_weekly_level_builds_on_previous_week(tmp_path):
    store = Store(tmp_path)
    store.save_json("weekly/2026-W44.json", {"scores": {}, "level_after": 3.0})
    finished_week(store)
    assert build_weekly(FakeLLM([LLM_PART]), store, WEEK, GOAL)["level_before"] == 3.0


def test_prompt_changes_with_level():
    low = build_system_prompt("daily", PLAN, MEMORY, 0, level=1.0)
    high = build_system_prompt("daily", PLAN, MEMORY, 0, level=6.5)
    assert "1.0 / 10" in low and "6.5 / 10" in high
    assert "idioms" in high.lower() and "avoid idioms" in low.lower()


def test_chat_uses_current_level(make_app, tmp_path):
    store = Store(tmp_path / "data")
    store.save_json("weekly/2026-W44.json", {"scores": {}, "level_after": 4.2})
    app = make_app([{"reply": "Hey!"}], store=store)
    app.start_chat("daily")
    assert app.conversation.level == 4.2


def test_weekly_view_shows_level_line(make_app, tmp_path):
    store = Store(tmp_path / "data")
    store.save_json("weekly/2026-W45.json", {"week": "2026-W45", "scores": {}, "reasons": {}, "letter": "x",
                                             "level_before": 1.0, "level_after": 1.6})
    app = make_app(store=store)
    app.show("weekly")
    assert "다음 주부터 대화가 조금 더 자연스러워져요 (레벨 1.0 → 1.6)" in all_text(app.views["weekly"])
