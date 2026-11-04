from talk.llm import FakeLLM, LLMError
from talk.memory import finish_session, load_memory
from talk.models import Correction, Message, Mistake, Session, TurnResult
from talk.store import Store

SUMMARY = {"topic_summary": "Talked about weekend plans.", "new_facts": ["Likes hiking"]}


def session(sid, date, mistakes=(), targets=(), corr=None, help_ko=None, help_expr=None, text="I very like it"):
    return Session(
        id=sid, date=date, mode="daily", topic="주말 계획", style="ai_story", started=f"{date}T09:00:00",
        seconds=600,
        messages=[Message("ai", "Hi", "t"), Message("user", text, "t", correction=corr, help_ko=help_ko),
                  Message("ai", "Nice", "t")],
        turns=[TurnResult("Nice", corr, help_ko, False, False, list(mistakes), list(targets), help_expr)],
    )


VERY = Mistake("very + verb", "I very like it", "I really like it", "grammar")


def test_new_mistake_recorded(tmp_path):
    store = Store(tmp_path)
    finish_session(FakeLLM([SUMMARY]), store, session("a", "2026-11-04", [VERY]))
    m = load_memory(store)["mistakes"]["very + verb"]
    assert m["count"] == 1 and m["first_seen"] == "2026-11-04" and m["native"] == "I really like it"
    assert load_memory(store)["facts"] == ["Likes hiking"]
    assert load_memory(store)["topics"][0]["summary"] == "Talked about weekend plans."


def test_repeat_on_later_day_counts_and_reported(tmp_path):
    store = Store(tmp_path)
    finish_session(FakeLLM([SUMMARY]), store, session("a", "2026-11-03", [VERY]))
    out = finish_session(FakeLLM([SUMMARY]), store, session("b", "2026-11-04", [VERY]))
    assert out.repeated == [{"key": "very + verb", "original": "I very like it", "native": "I really like it",
                             "count": 2, "first_seen": "2026-11-03"}]
    assert load_memory(store)["mistakes"]["very + verb"]["last_seen"] == "2026-11-04"


def test_same_day_repeat_counts_but_not_repeated(tmp_path):
    store = Store(tmp_path)
    out = finish_session(FakeLLM([SUMMARY]), store, session("a", "2026-11-04", [VERY, VERY]))
    assert out.repeated == []
    assert load_memory(store)["mistakes"]["very + verb"]["count"] == 2


def test_voice_sensitive_not_saved(tmp_path):
    store = Store(tmp_path)
    m = Mistake("articles", "go to park", "go to the park", "articles", voice_sensitive=True)
    out = finish_session(FakeLLM([SUMMARY]), store, session("a", "2026-11-04", [m]))
    assert load_memory(store)["mistakes"] == {} and out.repeated == []


def test_now_correct_updates_last_correct(tmp_path):
    store = Store(tmp_path)
    finish_session(FakeLLM([SUMMARY]), store, session("a", "2026-11-03", [VERY]))
    out = finish_session(FakeLLM([SUMMARY]), store, session("b", "2026-11-04", targets=["very + verb", "unknown"]))
    assert out.now_correct == [{"key": "very + verb", "native": "I really like it"}]
    assert load_memory(store)["mistakes"]["very + verb"]["last_correct"] == "2026-11-04"


def test_learned_includes_corrections_and_help(tmp_path):
    store = Store(tmp_path)
    corr = Correction("I really like it.", "very는 동사를 꾸미지 않아요.")
    out = finish_session(FakeLLM([SUMMARY]), store, session("a", "2026-11-04", corr=corr))
    assert out.learned == [{"original": "I very like it", "native": "I really like it.",
                            "why_ko": "very는 동사를 꾸미지 않아요."}]
    out2 = finish_session(FakeLLM([SUMMARY]), store, session(
        "b", "2026-11-04", help_ko="'예약 변경'은 change my reservation", help_expr="change my reservation",
        text="예약 변경 영어로?"))
    assert out2.learned == [{"original": "예약 변경 영어로?", "native": "change my reservation",
                             "why_ko": "'예약 변경'은 change my reservation"}]


def test_summary_failure_still_finishes(tmp_path):
    store = Store(tmp_path)
    finish_session(FakeLLM([LLMError("busy")]), store, session("a", "2026-11-04", [VERY]))
    mem = load_memory(store)
    assert mem["topics"][0]["summary"] == "주말 계획" and "very + verb" in mem["mistakes"]


def test_finish_is_idempotent(tmp_path):
    store = Store(tmp_path)
    s = session("a", "2026-11-04", [VERY])
    finish_session(FakeLLM([SUMMARY]), store, s)
    finish_session(FakeLLM([]), store, s)
    assert load_memory(store)["mistakes"]["very + verb"]["count"] == 1
    assert len(load_memory(store)["topics"]) == 1


def test_topics_capped_at_30(tmp_path):
    store = Store(tmp_path)
    for i in range(32):
        finish_session(FakeLLM([SUMMARY]), store, session(f"s{i:02d}", "2026-11-04"))
    assert len(load_memory(store)["topics"]) == 30
