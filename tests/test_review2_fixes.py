import threading
from datetime import date

from talk import startup
from talk.llm import FakeLLM, LLMError
from talk.memory import load_memory
from talk.planner import get_plan
from talk.reports import build_weekly, finalize_session, load_daily
from talk.startup import run_startup
from talk.store import Store
from tests.conftest import pump
from tests.test_weekly import GOAL, LLM_PART, VERY, WEEK, finished_week, sess


def test_startup_builds_missed_weeks(tmp_path):
    store = Store(tmp_path)
    finished_week(store)  # 2026-W45
    assert run_startup(FakeLLM([LLM_PART]), store, GOAL, None, today=date(2026, 11, 18)) is True  # W47
    assert store.load_json(f"weekly/{WEEK}.json", None) is not None


def test_startup_regenerates_todays_plan_after_new_weekly(tmp_path):
    store = Store(tmp_path)
    finished_week(store, mistakes=[VERY, VERY])
    today = date(2026, 11, 9)
    store.save_json("memory.json", dict(load_memory(store), mistakes=dict(
        load_memory(store)["mistakes"], other={"original": "o", "native": "n", "area": "g", "count": 99,
                                               "first_seen": "2026-11-01", "last_seen": "2026-11-07",
                                               "last_correct": None, "voice_only": False})))
    assert get_plan(store, today).targets[0] == "other"  # 앱을 켜자마자 (평가서 전에) 만들어진 계획
    run_startup(FakeLLM([LLM_PART]), store, GOAL, None, today=today)
    assert get_plan(store, today).targets[0] == "very + verb"  # 새 평가서의 next_targets가 먼저


def test_concurrent_finalize_keeps_both(tmp_path):
    for round_ in range(15):
        store = Store(tmp_path / str(round_))
        a, b = sess("a", "2026-11-04", mistakes=[VERY]), sess("b", "2026-11-04", mistakes=[VERY])
        summary = {"topic_summary": "s", "new_facts": []}
        threads = [threading.Thread(target=finalize_session, args=(FakeLLM([summary]), store, s)) for s in (a, b)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert load_daily(store, "2026-11-04")["seconds"] == 2520
        assert sorted(load_memory(store)["processed"]) == ["a", "b"]
        assert load_memory(store)["mistakes"]["very + verb"]["count"] == 2


def test_week_labels_distinct_across_years():
    from talk.reports import week_label
    today = date(2027, 6, 1)
    assert week_label("2027-W01", today) == "1월 첫째 주 평가서"
    assert week_label("2026-W02", today) == "2026년 1월 첫째 주 평가서"


def test_weekly_view_menu_distinct_across_years(make_app, tmp_path):
    store = Store(tmp_path / "data")
    for w in ("2026-W02", "2027-W01"):
        store.save_json(f"weekly/{w}.json", {"week": w, "scores": {}, "reasons": {}, "letter": w})
    app = make_app(store=store)
    app.show("weekly")
    view = app.views["weekly"]
    assert len(view.weeks) == 2
    for title, wid in view.weeks.items():
        view.render(wid)
        assert view.shown == wid


def test_bad_llm_score_falls_back(tmp_path):
    store = Store(tmp_path)
    store.save_json("weekly/2026-W44.json", {"scores": {"willpower": 6.0}})
    finished_week(store)
    w = build_weekly(FakeLLM([dict(LLM_PART, willpower="high", speaking=float("nan"), leadership=None)]),
                     store, WEEK, GOAL)
    assert w["scores"]["willpower"] == 6.0       # 지난주 점수 유지
    assert w["scores"]["speaking"] is None and w["scores"]["leadership"] is None  # "—"로 표시


def test_startup_continues_after_one_session_fails(tmp_path, monkeypatch):
    store = Store(tmp_path)
    store.save_session(sess("bad", "2026-11-04"))
    store.save_session(sess("good", "2026-11-04"))
    real = startup.finalize_session

    def flaky(llm, store_, s):
        if s.id == "bad":
            raise OSError("disk")
        return real(llm, store_, s)

    monkeypatch.setattr(startup, "finalize_session", flaky)
    run_startup(FakeLLM([{"topic_summary": "s", "new_facts": []}]), store, GOAL, None, today=date(2026, 11, 4))
    assert store.load_session("good").finished is True


def test_startup_refresh_keeps_user_mode_choice(make_app):
    app = make_app([])
    view = app.views["start"]
    view.pick("pattern")
    app.startup_jobs()
    pump(app, lambda: False, timeout=0.5)
    assert view.selected_mode == "pattern"
