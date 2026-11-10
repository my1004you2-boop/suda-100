from talk.memory import SessionOutcome
from talk.reports import update_daily
from talk.store import Store
from tests.test_store import make_session


def all_text(widget) -> str:
    out = []
    for w in widget.winfo_children():
        try:
            out.append(str(w.cget("text")))
        except Exception:
            pass
        if hasattr(w, "get") and w.winfo_class() == "Text":  # 선택 가능한 글자 (SelectableText)
            out.append(w.get("1.0", "end-1c"))
        out.append(all_text(w))
    return "\n".join(out)


def test_daily_view_shows_sections(make_app, tmp_path):
    store = Store(tmp_path / "data")
    s = make_session("20261104-090000")
    s.seconds = 1320
    update_daily(store, s, SessionOutcome(
        repeated=[{"key": "very + verb", "original": "I very like it", "native": "I really like it",
                   "count": 3, "first_seen": "2026-10-28"}],
        now_correct=[{"key": "be going to", "native": "I'm going to"}],
        learned=[{"original": "i cant choose one of them", "native": "I can't decide between them.", "why_ko": "x"}],
    ))
    app = make_app(store=store)
    app.show("daily")
    text = all_text(app.views["daily"])
    assert "11월 4일 (수)" in text and "22분" in text
    assert "오늘 배운 원어민 표현" in text and "I can't decide between them." in text
    assert "🔁 또 나온 표현" in text and "3번째" in text and "처음 10월 28일" in text
    assert "✨ 이제 맞게 쓴 표현" in text and "I'm going to" in text


def test_daily_view_hides_empty_sections(make_app, tmp_path):
    store = Store(tmp_path / "data")
    update_daily(store, make_session("20261104-090000"), SessionOutcome())
    app = make_app(store=store)
    app.show("daily")
    text = all_text(app.views["daily"])
    assert "또 나온 표현" not in text and "이제 맞게 쓴 표현" not in text


def test_daily_view_empty_message(make_app):
    app = make_app()
    app.show("daily")
    assert "아직 리포트가 없어요" in all_text(app.views["daily"])
