from datetime import datetime

from talk.models import Correction, Message, Mistake, Session, TurnResult
from talk.store import Store, new_session_id


def make_session(sid="20261104-213005", date="2026-11-04", finished=False):
    mistake = Mistake(key="very + verb", original="I very like it", native="I really like it", area="adverb")
    corr = Correction(native="I really like it.", why_ko="very는 동사를 꾸미지 않아요.", extend=None)
    return Session(
        id=sid, date=date, mode="daily", topic="주말 계획", style="ai_story",
        started=f"{date}T21:30:05", seconds=60,
        messages=[
            Message(role="ai", text="Hi!", ts="t1"),
            Message(role="user", text="I very like it", ts="t2", via_voice=True, correction=corr),
        ],
        turns=[TurnResult(reply="Nice!", correction=corr, help_ko=None, user_asked_question=False,
                          user_led=False, mistakes=[mistake], targets_used_correctly=[])],
        finished=finished,
    )


def test_session_roundtrip(tmp_path):
    store = Store(tmp_path)
    s = make_session()
    store.save_session(s)
    assert store.load_session(s.id) == s


def test_list_sessions_by_date(tmp_path):
    store = Store(tmp_path)
    store.save_session(make_session("20261104-090000"))
    store.save_session(make_session("20261104-210000"))
    store.save_session(make_session("20261105-090000", date="2026-11-05"))
    ids = [s.id for s in store.list_sessions("2026-11-04")]
    assert ids == ["20261104-090000", "20261104-210000"]
    assert len(store.list_sessions()) == 3


def test_unfinished(tmp_path):
    store = Store(tmp_path)
    store.save_session(make_session("20261104-090000", finished=True))
    store.save_session(make_session("20261104-210000"))
    assert [s.id for s in store.unfinished_sessions()] == ["20261104-210000"]


def test_session_date_is_start_date(tmp_path):
    store = Store(tmp_path)
    started = datetime(2026, 11, 4, 23, 50)
    s = make_session(new_session_id(started), date=started.date().isoformat())
    s.seconds = 1200  # 자정을 넘겨 00:10에 저장
    store.save_session(s)
    assert store.load_session(s.id).date == "2026-11-04"
    assert new_session_id(started) == "20261104-235000"


def test_load_json_default_when_missing_or_broken(tmp_path):
    store = Store(tmp_path)
    assert store.load_json("memory.json", {"a": 1}) == {"a": 1}
    store.save_json("daily/2026-11-04.json", {"x": 2})
    assert store.load_json("daily/2026-11-04.json", None) == {"x": 2}
    (tmp_path / "memory.json").write_text("{oops", encoding="utf-8")
    assert store.load_json("memory.json", {}) == {}
