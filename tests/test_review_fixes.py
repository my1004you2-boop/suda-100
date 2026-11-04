import threading
import tkinter as tk

import httpx

from talk.conversation import Conversation
from talk.llm import FakeLLM, GeminiLLM, LLMError
from talk.memory import finish_session, load_memory
from talk.reports import load_daily
from talk.store import Store
from talk.worker import Worker
from tests.conftest import pump
from tests.test_conversation import MEMORY, PLAN, turn
from tests.test_memory import SUMMARY, VERY, session
from tests.test_store import make_session


def test_worker_survives_callback_exception():
    root = tk.Tk()
    try:
        w = Worker(root)
        got = []
        w.run(lambda: 1, lambda r: 1 / 0)
        pump(root, lambda: False, timeout=0.3)
        w.run(lambda: 2, got.append)
        assert pump(root, lambda: got == [2])
    finally:
        root.destroy()


def test_discarded_conversation_opening_does_not_save(tmp_path):
    store = Store(tmp_path)
    conv = Conversation(FakeLLM([{"reply": "Hi!"}]), store, PLAN, "daily", MEMORY)
    conv.discard()
    conv.opening()
    assert store.list_sessions() == []


def test_end_chat_during_opening(make_app):
    app = make_app([{"reply": "Hey!"}, {"reply": "unused"}])
    app.start_chat("daily")
    app.end_chat()  # 첫 마디가 오기 전에 끝내기
    pump(app, lambda: False, timeout=0.5)
    assert app.current == "start" and app.services.store.list_sessions() == []
    app.start_chat("daily")  # 다음 대화가 정상적으로 동작해야 한다
    assert pump(app, lambda: app.views["chat"].bubble_count == 1)


def test_concurrent_session_saves(tmp_path):
    store = Store(tmp_path)
    s = make_session()
    errors = []

    def hammer():
        try:
            for _ in range(150):
                store.save_session(s)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=hammer) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and store.load_session(s.id) == s


def test_finish_session_idempotent_without_finished_flag(tmp_path):
    store = Store(tmp_path)
    s = session("a", "2026-11-03", [VERY])
    finish_session(FakeLLM([SUMMARY]), store, s)
    assert s.finished is False  # 표시는 finalize의 마지막 단계에서
    finish_session(FakeLLM([]), store, s)  # 다시 불러도 AI를 부르지 않고 두 번 세지 않는다
    assert load_memory(store)["mistakes"]["very + verb"]["count"] == 1


def test_finalize_writes_daily_then_marks_finished(tmp_path):
    store = Store(tmp_path)
    finish_session(FakeLLM([SUMMARY]), store, session("old", "2026-11-03", [VERY]))
    s = session("a", "2026-11-04", [VERY])
    finish_session(FakeLLM([SUMMARY]), store, s)  # 여기서 앱이 꺼졌다고 치자
    from talk.reports import finalize_session
    report = finalize_session(FakeLLM([]), store, s)
    assert report["sessions"][0]["id"] == "a" and report["repeated"][0]["count"] == 2
    assert store.load_session("a").finished is True
    assert load_daily(store, "2026-11-04")["seconds"] == 600


def test_gemini_client_has_timeout():
    llm = GeminiLLM("k", "m")
    assert llm._http_options().timeout == 30_000


def test_timeout_is_retried():
    waits = []
    llm = GeminiLLM("k", "m", sleep=waits.append)
    seq = [httpx.ReadTimeout("slow"), '{"a": 1}']

    def call(*a):
        item = seq.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
    llm._call = call
    assert llm.generate_json("s", [], {}) == {"a": 1} and waits == [2]


def test_retry_uses_current_settings_llm(make_app):
    app = make_app([LLMError("AI에 연결하지 못했어요.")])
    app.start_chat("daily")
    view = app.views["chat"]
    assert pump(app, lambda: view._pending and not view.sending and view.bubble_count == 0
                and "연결하지" in view.status_text())
    fresh = FakeLLM([{"reply": "Hello again!"}])
    app.services.llm_factory = lambda s: fresh  # 사용자가 설정에서 키를 고침
    view.retry_open()
    assert pump(app, lambda: view.bubble_count == 1)


def test_voice_turn_failure_keeps_sentence(make_app):
    app = make_app([{"reply": "Hey!"}, LLMError("잠시 후 다시 시도해 주세요.")])
    app.start_chat("daily")
    view = app.views["chat"]
    assert pump(app, lambda: view.bubble_count == 1)
    view.send("I go to park yesterday", via_voice=True)
    assert pump(app, lambda: not view.sending and "다시 시도" in view.error_label.cget("text"))
    assert view.input.get("1.0", "end").strip() == "I go to park yesterday"
