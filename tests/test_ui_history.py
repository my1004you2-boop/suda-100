from talk.models import Correction, Message
from talk.store import Store
from tests.test_store import make_session
from tests.test_ui_daily import all_text


def store_with_sessions(tmp_path):
    store = Store(tmp_path / "data")
    old = make_session("20261103-090000", date="2026-11-03", finished=True)
    new = make_session("20261104-213000", finished=True)
    new.seconds = 1320
    new.messages = [Message("ai", "Hey!", "t", translation_ko="안녕!"),
                    Message("user", "i cant choose", "t", correction=Correction("I can't decide.", "decide가 자연스러워요"))]
    store.save_session(old)
    store.save_session(new)
    return store


def test_history_lists_sessions_newest_first(make_app, tmp_path):
    app = make_app(store=store_with_sessions(tmp_path))
    app.show("history")
    view = app.views["history"]
    assert [b.session_id for b in view.items] == ["20261104-213000", "20261103-090000"]
    assert "11월 4일 21:30 · ☕ 일상 대화 · 주말 계획 · 22분" in view.items[0].cget("text")


def test_history_opens_session_readonly(make_app, tmp_path):
    app = make_app(store=store_with_sessions(tmp_path))
    app.show("history")
    view = app.views["history"]
    assert view.opened == "20261104-213000"  # 가장 최근 대화가 먼저 열린다
    text = all_text(view.detail)
    assert "Hey!" in text and "I can't decide." in text
    assert {c.kind for c in view.cards} == {"fix", "trans"}
    view.items[1].invoke()
    assert view.opened == "20261103-090000"


def test_history_empty(make_app):
    app = make_app()
    app.show("history")
    assert "아직 대화 기록이 없어요" in all_text(app.views["history"])
