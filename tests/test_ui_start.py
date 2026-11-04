from datetime import date

from talk.config import Settings
from talk.planner import get_plan
from talk.store import Store
from tests.test_store import make_session


def test_start_view_preselects_recommended(make_app):
    app = make_app()
    view = app.views["start"]
    plan = get_plan(app.services.store, date.today())
    assert view.selected_mode == plan.recommended
    view.select("verb")
    assert view.selected_mode == "verb"
    assert "오늘의 동사" in view.cards["verb"].topic_label.cget("text")


def test_start_without_key_goes_to_settings(make_app):
    app = make_app(settings=Settings(api_key=""))
    started = []
    app.start_chat = lambda mode: started.append(mode)
    app.views["start"].start()
    assert started == [] and app.current == "settings"
    assert "API 키" in app.views["settings"].status.cget("text")


def test_start_calls_start_chat(make_app):
    app = make_app()
    started = []
    app.start_chat = lambda mode: started.append(mode)
    app.views["start"].select("business")
    app.views["start"].start()
    assert started == ["business"]


def test_week_marks_days_with_sessions(make_app, tmp_path):
    store = Store(tmp_path / "data")
    today = date.today()
    store.save_session(make_session("x", date=today.isoformat()))
    app = make_app(store=store)
    view = app.views["start"]
    view.refresh()
    assert view.day_marks[today.weekday()] == "done"


def test_greeting_after_long_absence(make_app, tmp_path):
    store = Store(tmp_path / "data")
    store.save_session(make_session("old", date="2020-01-01", finished=True))
    app = make_app(store=store)
    assert "다시 와서 반가워요" in app.views["start"].greeting.cget("text")
