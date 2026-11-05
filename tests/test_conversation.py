from datetime import datetime

import pytest

from talk.conversation import Conversation
from talk.llm import FakeLLM, LLMError
from talk.models import DayPlan
from talk.prompts import build_system_prompt
from talk.store import Store
from tests.test_store import make_session

NOW = datetime(2026, 11, 4, 21, 30, 5)
PLAN = DayPlan(
    date="2026-11-04",
    topics={"daily": "주말에 뭐 할지 고민하기", "business": "회의 일정 잡기",
            "verb": "오늘의 동사: get", "pattern": "used to, be going to"},
    verb="get", patterns=["used to", "be going to"], style="ai_disagree",
    recommended="daily", targets=["very + verb"],
)
MEMORY = {
    "topics": [{"date": "2026-11-03", "mode": "daily", "topic": "영화", "summary": "Talked about Dune."}],
    "facts": ["Works as a designer"],
    "mistakes": {"very + verb": {"original": "I very like it", "native": "I really like it", "area": "grammar",
                                 "count": 2, "first_seen": "2026-10-28", "last_seen": "2026-11-01",
                                 "last_correct": None, "voice_only": False}},
}


def turn(reply="Ha, tough call!", **kw):
    base = {"reply": reply, "correction": None, "help_ko": None, "help_expr": None,
            "user_asked_question": False, "user_led": False, "mistakes": [], "targets_used_correctly": []}
    base.update(kw)
    return base


def make_conv(tmp_path, responses, mode="daily"):
    store = Store(tmp_path)
    llm = FakeLLM([{"reply": "Hey! Any plans for the weekend?"}] + responses)
    conv = Conversation(llm, store, PLAN, mode, MEMORY, now=lambda: NOW)
    conv.opening()
    return conv, store, llm


def test_send_appends_messages_and_saves(tmp_path):
    corr = {"native": "I can't decide between them.", "why_ko": "두 개 중엔 decide between", "extend": None}
    mistake = {"key": "choose one of → decide between", "original": "i cant choose one of them",
               "native": "I can't decide between them.", "area": "word choice", "voice_sensitive": False}
    conv, store, _ = make_conv(tmp_path, [turn(correction=corr, mistakes=[mistake])])
    r = conv.send("i cant choose one of them")
    assert r.correction.native == "I can't decide between them."
    assert r.mistakes[0].key == "choose one of → decide between"
    assert [m.role for m in conv.session.messages] == ["ai", "user", "ai"]
    saved = store.load_session(conv.session.id)
    assert saved.messages[1].correction is not None and saved.messages[2].text == "Ha, tough call!"
    assert saved.date == "2026-11-04" and saved.topic == "주말에 뭐 할지 고민하기"


def test_help_turn_kept_on_user_message(tmp_path):
    conv, _, _ = make_conv(tmp_path, [turn(help_ko="'예약 변경'은 change my reservation이에요.",
                                           help_expr="change my reservation")])
    r = conv.send("I want to 예약 변경 for tomorrow")
    assert conv.session.messages[1].help_ko.startswith("'예약 변경'")
    assert r.help_expr == "change my reservation"


@pytest.mark.parametrize("bad", [LLMError("busy"), {"reply": ""}, {"nope": 1}])
def test_llm_error_leaves_session_unchanged(tmp_path, bad):
    conv, store, _ = make_conv(tmp_path, [bad])
    with pytest.raises(LLMError):
        conv.send("hello")
    assert len(conv.session.messages) == 1
    assert len(store.load_session(conv.session.id).messages) == 1


def test_question_streak_passed_to_prompt(tmp_path):
    conv, _, llm = make_conv(tmp_path, [turn("What movie?"), turn("Do you like it?")])
    conv.send("I like movies")          # AI 질문 1, 2 (opening 포함)
    assert "Do not ask a question" not in llm.calls[-1][0]
    conv.send("Sci-fi")
    assert "Do not ask a question" in llm.calls[-1][0]


def test_voice_flag_stored_and_hinted(tmp_path):
    conv, _, llm = make_conv(tmp_path, [turn()])
    conv.send("I go to park yesterday", via_voice=True)
    assert conv.session.messages[1].via_voice is True
    assert conv.session.messages[1].text == "I go to park yesterday"
    assert "speech recognition" in llm.calls[-1][1][-1][1]


def test_history_roles(tmp_path):
    conv, _, llm = make_conv(tmp_path, [turn()])
    conv.send("hi")
    assert [r for r, _ in llm.calls[-1][1]] == ["model", "user"]


def test_prompt_contains_targets_and_style():
    p = build_system_prompt("daily", PLAN, MEMORY, 0)
    assert "I really like it" in p                  # 은근히 연습할 원어민 표현
    assert "disagree" in p.lower()                  # 오늘의 대화 방식
    assert "주말에 뭐 할지 고민하기" in p
    assert "Works as a designer" in p and "Talked about Dune." in p
    assert "very + verb" in p                        # 기존 실수 키 목록
    assert "help_ko" in p and "lowercase" in p


def test_prompt_mode_specific():
    assert "get" in build_system_prompt("verb", PLAN, MEMORY, 0)
    assert "used to" in build_system_prompt("pattern", PLAN, MEMORY, 0)
    assert "회의 일정 잡기" in build_system_prompt("business", PLAN, MEMORY, 0)


def test_prompt_long_absence_greeting(tmp_path):
    store = Store(tmp_path)
    store.save_session(make_session("20261028-090000", date="2026-10-28", finished=True))
    llm = FakeLLM([{"reply": "Hey, good to see you again!"}])
    Conversation(llm, store, PLAN, "daily", MEMORY, now=lambda: NOW).opening()
    assert "nice to see them again" in llm.calls[0][0]


def test_add_seconds(tmp_path):
    conv, _, _ = make_conv(tmp_path, [])
    conv.add_seconds(5)
    assert conv.session.seconds == 5


def test_ai_translation_stored(tmp_path):
    store = Store(tmp_path)
    llm = FakeLLM([{"reply": "Hey!", "reply_ko": "안녕!"}, turn(reply_ko="하하, 고르기 어렵네!")])
    conv = Conversation(llm, store, PLAN, "daily", MEMORY, now=lambda: NOW)
    conv.opening()
    conv.send("hi")
    assert conv.session.messages[0].translation_ko == "안녕!"
    assert conv.session.messages[-1].translation_ko == "하하, 고르기 어렵네!"
    assert store.load_session(conv.session.id).messages[-1].translation_ko == "하하, 고르기 어렵네!"
    assert "reply_ko" in llm.calls[-1][0]


# --- 분석용 기록 정리 (docs/데이터분석과제.md) ---

def test_area_normalized_to_fixed_list(tmp_path):
    ms = [{"key": "a", "original": "x", "native": "y", "area": " Vocabulary "},
          {"key": "b", "original": "x", "native": "y", "area": "phrasal_flow"}]
    conv, _, _ = make_conv(tmp_path, [turn(mistakes=ms)])
    r = conv.send("hi")
    assert [m.area for m in r.mistakes] == ["vocabulary", "other"]


def test_turn_schema_restricts_area():
    from talk.prompts import AREAS, TURN_SCHEMA
    area = TURN_SCHEMA["properties"]["mistakes"]["items"]["properties"]["area"]
    assert area["enum"] == list(AREAS)


def test_prompt_shows_existing_keys_with_native_and_asks_specific_keys():
    p = build_system_prompt("daily", PLAN, MEMORY, 0)
    assert 'very + verb = "I really like it"' in p
    assert "not a broad category" in p


def test_prompt_limits_existing_keys_to_most_recent():
    mistakes = {f"k{i:02d}": {"original": "o", "native": f"n{i}", "area": "grammar", "count": 1,
                              "first_seen": "2026-11-01", "last_seen": f"2026-11-{i % 28 + 1:02d}"}
                for i in range(60)}
    p = build_system_prompt("daily", PLAN, {**MEMORY, "mistakes": mistakes}, 0)
    from talk.prompts import MAX_KNOWN_KEYS
    assert sum(f'k{i:02d} = "' in p for i in range(60)) == MAX_KNOWN_KEYS


def test_session_records_model_and_prompt_version(tmp_path):
    from talk.prompts import PROMPT_VERSION
    conv, store, _ = make_conv(tmp_path, [])
    saved = store.load_session(conv.session.id)
    assert saved.model == "fake" and saved.prompt_version == PROMPT_VERSION


def test_old_session_file_without_model_still_loads():
    from talk.models import Session
    s = Session.from_dict({"id": "x", "date": "2026-11-04", "mode": "daily", "topic": "t", "style": "ai_story",
                           "started": "2026-11-04T10:00:00", "seconds": 0})
    assert s.model == "" and s.prompt_version == ""


def test_prompt_hides_broad_legacy_keys():
    from talk.prompts import BROAD_KEYS
    mistakes = {**MEMORY["mistakes"],
                "natural_phrasing": {"original": "so so", "native": "It was so-so.", "area": "grammar",
                                     "last_seen": "2026-11-04"}}
    p = build_system_prompt("daily", PLAN, {**MEMORY, "mistakes": mistakes}, 0)
    assert "natural_phrasing" in BROAD_KEYS
    assert 'natural_phrasing = "' not in p and 'very + verb = "' in p
