from talk.config import Settings
from talk.memory import SessionOutcome
from talk.reports import daily_dates, goal_progress, load_daily, update_daily
from talk.store import Store
from tests.test_store import make_session

LEARNED = [{"original": "I very like it", "native": "I really like it", "why_ko": "very 대신 really"}]
REPEATED = [{"key": "very + verb", "original": "I very like it", "native": "I really like it",
             "count": 2, "first_seen": "2026-11-01"}]


def outcome(count=2):
    rep = [dict(REPEATED[0], count=count)]
    return SessionOutcome(repeated=rep, now_correct=[{"key": "be going to", "native": "I'm going to"}],
                          learned=list(LEARNED))


def test_first_session_creates_report(tmp_path):
    store = Store(tmp_path)
    s = make_session("20261104-090000")
    r = update_daily(store, s, outcome())
    assert r["date"] == "2026-11-04" and r["seconds"] == 60 and r["user_messages"] == 1
    assert r["sessions"] == [{"id": s.id, "mode": "daily", "topic": "주말 계획", "seconds": 60}]
    assert r["learned"] == LEARNED and r["repeated"][0]["count"] == 2 and len(r["now_correct"]) == 1
    assert load_daily(store, "2026-11-04") == r


def test_second_session_merges(tmp_path):
    store = Store(tmp_path)
    update_daily(store, make_session("20261104-090000"), outcome(2))
    r = update_daily(store, make_session("20261104-210000"), outcome(3))
    assert r["seconds"] == 120 and r["user_messages"] == 2 and len(r["sessions"]) == 2
    assert len(r["learned"]) == 2
    assert r["repeated"] == [dict(REPEATED[0], count=3)]
    assert len(r["now_correct"]) == 1


def test_update_twice_same_session_no_duplicate(tmp_path):
    store = Store(tmp_path)
    s = make_session("20261104-090000")
    update_daily(store, s, outcome())
    r = update_daily(store, s, outcome())
    assert r["seconds"] == 60 and len(r["sessions"]) == 1 and len(r["learned"]) == 1


def test_goal_progress_sums_sessions_and_live(tmp_path):
    store = Store(tmp_path)
    s = make_session("20261104-090000")
    s.seconds = 600
    update_daily(store, s, outcome())
    assert goal_progress(store, "2026-11-04", Settings(daily_goal_min=20), live_seconds=125) == (12, 20)
    assert goal_progress(store, "2026-11-05", Settings(), 0) == (0, 20)


def test_daily_dates_newest_first(tmp_path):
    store = Store(tmp_path)
    update_daily(store, make_session("20261103-090000", date="2026-11-03"), outcome())
    update_daily(store, make_session("20261104-090000"), outcome())
    assert daily_dates(store) == ["2026-11-04", "2026-11-03"]
    assert load_daily(store, "2026-01-01") is None
