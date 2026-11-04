from datetime import date, timedelta

from talk import content
from talk.planner import STYLES, get_plan
from talk.store import Store
from tests.test_store import make_session

DAY = date(2026, 11, 4)


def test_plan_fixed_for_day(tmp_path):
    store = Store(tmp_path)
    p1 = get_plan(store, DAY)
    store.save_json("memory.json", {"topics": [], "facts": [], "mistakes": {
        "x": {"area": "grammar", "count": 9, "last_seen": "2026-11-04", "voice_only": False}}})
    p2 = get_plan(store, DAY)
    assert p1 == p2
    assert store.load_json("plans/2026-11-04.json", None) == p1.to_dict()


def test_style_rotates(tmp_path):
    store = Store(tmp_path)
    styles = [get_plan(store, DAY + timedelta(days=i)).style for i in range(6)]
    assert sorted(styles) == sorted(STYLES)
    assert get_plan(store, DAY).style == STYLES[DAY.toordinal() % 6]


def test_daily_topic_not_repeated_within_14_days(tmp_path):
    store = Store(tmp_path)
    days = [DAY + timedelta(days=i) for i in range(14)]
    topics = [get_plan(store, d).topics["daily"] for d in days]
    fresh = [t for t in topics if not t.startswith("이어서: ")]
    assert len(fresh) == len(set(fresh))
    assert all(t in content.TOPICS["daily"] for t in fresh)


def test_continue_last_topic_every_4th_day(tmp_path):
    store = Store(tmp_path)
    d = next(DAY + timedelta(days=i) for i in range(4) if (DAY + timedelta(days=i)).toordinal() % 4 == 0)
    store.save_session(make_session("20261101-090000", date="2026-11-01"))  # 일상 대화, 주제 "주말 계획"
    assert get_plan(store, d).topics["daily"] == "이어서: 주말 계획"
    other = d + timedelta(days=1)
    assert not get_plan(store, other).topics["daily"].startswith("이어서: ")


def test_verb_and_pattern_topics(tmp_path):
    p = get_plan(Store(tmp_path), DAY)
    assert p.topics["verb"] == "오늘의 동사: " + p.verb
    assert p.topics["pattern"] == ", ".join(p.patterns) and len(p.patterns) == 2


def test_least_used_verb_chosen(tmp_path):
    store = Store(tmp_path)
    first = get_plan(store, DAY).verb
    assert first == content.VERBS[0]
    assert get_plan(store, DAY + timedelta(days=1)).verb == content.VERBS[1]


def test_targets_prefer_weekly_next_targets_then_count(tmp_path):
    store = Store(tmp_path)
    store.save_json("weekly/2026-W44.json", {"next_targets": ["articles"]})
    store.save_json("memory.json", {"topics": [], "facts": [], "mistakes": {
        "articles": {"area": "grammar", "count": 1, "last_seen": "2026-10-20", "voice_only": False},
        "very + verb": {"area": "grammar", "count": 5, "last_seen": "2026-11-01", "voice_only": False},
        "tense": {"area": "grammar", "count": 5, "last_seen": "2026-11-03", "voice_only": False},
        "in on at": {"area": "grammar", "count": 2, "last_seen": "2026-11-03", "voice_only": False},
    }})
    assert get_plan(store, DAY).targets == ["articles", "tense", "very + verb"]


def test_voice_only_mistakes_excluded(tmp_path):
    store = Store(tmp_path)
    store.save_json("memory.json", {"topics": [], "facts": [], "mistakes": {
        "a/the": {"area": "grammar", "count": 9, "last_seen": "2026-11-03", "voice_only": True},
        "tense": {"area": "grammar", "count": 1, "last_seen": "2026-11-03", "voice_only": False},
    }})
    assert get_plan(store, DAY).targets == ["tense"]


def test_recommended_is_least_used_mode(tmp_path):
    store = Store(tmp_path)
    assert get_plan(store, DAY).recommended == "daily"
    store.save_session(make_session("20261104-090000"))  # daily 1회
    assert get_plan(store, DAY + timedelta(days=1)).recommended == "business"


def test_recommended_business_when_target_is_business(tmp_path):
    store = Store(tmp_path)
    store.save_json("memory.json", {"topics": [], "facts": [], "mistakes": {
        "schedule a meeting": {"area": "business expression", "count": 2, "last_seen": "2026-11-03", "voice_only": False},
    }})
    store.save_session(make_session("20261103-090000", date="2026-11-03"))
    s = make_session("20261103-100000", date="2026-11-03")
    s.mode = "business"
    store.save_session(s)
    assert get_plan(store, DAY).recommended == "business"
