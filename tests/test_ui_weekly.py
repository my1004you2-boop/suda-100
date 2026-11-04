from datetime import date, timedelta

from talk.planner import week_id
from talk.store import Store
from tests.conftest import pump
from tests.test_ui_daily import all_text
from tests.test_weekly import LLM_PART, finished_week

WEEKLY = {
    "week": "2026-W45", "metrics": {}, "letter": "이번 주는 5일이나 대화하셨어요.",
    "scores": {"sincerity": 8.0, "willpower": 7.0, "speaking": 6.44, "understanding": None, "leadership": 5.0},
    "reasons": {"sincerity": "5일 · 하루 평균 21분", "speaking": "문장이 길어짐"},
    "weak_points": "관사 a/the 누락", "next_plan": "관사가 나오는 주제로", "next_targets": [],
}


def test_weekly_view_shows_scores_and_letter(make_app, tmp_path):
    store = Store(tmp_path / "data")
    store.save_json("weekly/2026-W45.json", WEEKLY)
    app = make_app(store=store)
    app.show("weekly")
    text = all_text(app.views["weekly"])
    assert "11월 첫째 주 평가서" in text and "이번 주는 5일이나 대화하셨어요." in text
    assert "6.4 / 10.0" in text and "8.0 / 10.0" in text
    assert "성실도" in text and "대화 주도력" in text and "교정 이해력" in text
    assert "이번 주는 연습 대상이 없었어요" in text
    assert "부족한 점" in text and "관사 a/the 누락" in text and "다음 주 방안" in text


def test_weekly_view_empty(make_app):
    app = make_app()
    app.show("weekly")
    assert "첫 평가서는 이번 주가 끝나면 도착해요" in all_text(app.views["weekly"])


def test_startup_banner_opens_weekly(make_app, tmp_path):
    store = Store(tmp_path / "data")
    last = date.today() - timedelta(days=7)
    monday = last - timedelta(days=last.weekday())
    finished_week(store, days=tuple((monday + timedelta(days=i)).isoformat() for i in range(3)))
    app = make_app([LLM_PART], store=store)
    app.startup_jobs()
    view = app.views["start"]
    assert pump(app, lambda: view.banner.winfo_ismapped())
    assert "지난주 평가서가 도착했어요" in view.banner.cget("text")
    assert store.load_json(f"weekly/{week_id(last)}.json", None) is not None
    view.banner.invoke()
    assert app.current == "weekly"
