import pytest
from google.genai import errors

from talk.llm import FakeLLM, GeminiLLM, LLMError


def rate_limit():
    return errors.ClientError(429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}})


def make_seq(items):
    items = list(items)

    def call(system, history, schema):
        item = items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
    return call


def make_llm(waits):
    return GeminiLLM("k", "m", sleep=lambda s: waits.append(s))


def test_retries_on_rate_limit_then_succeeds():
    waits = []
    llm = make_llm(waits)
    llm._call = make_seq([rate_limit(), rate_limit(), '{"a": 1}'])
    assert llm.generate_json("sys", [], {}) == {"a": 1}
    assert waits == [2, 5]


def test_gives_up_after_three_retries_with_korean_message():
    waits = []
    llm = make_llm(waits)
    llm._call = make_seq([rate_limit()] * 4)
    with pytest.raises(LLMError) as e:
        llm.generate_json("sys", [], {})
    assert "잠시 후 다시 시도해 주세요" in e.value.message_ko
    assert waits == [2, 5, 10]


def test_server_and_network_errors_are_retried():
    waits = []
    llm = make_llm(waits)
    llm._call = make_seq([errors.ServerError(503, {}), ConnectionError("down"), '{"ok": true}'])
    assert llm.generate_json("sys", [], {}) == {"ok": True}


def test_other_client_error_not_retried():
    waits = []
    llm = make_llm(waits)
    llm._call = make_seq([errors.ClientError(400, {"error": {"message": "bad key"}})])
    with pytest.raises(LLMError):
        llm.generate_json("sys", [], {})
    assert waits == []


@pytest.mark.parametrize("text", ["{oops", "", "[1, 2]"])
def test_invalid_json_raises_llmerror(text):
    llm = make_llm([])
    llm._call = make_seq([text])
    with pytest.raises(LLMError):
        llm.generate_json("sys", [], {})


def test_missing_api_key_raises_llmerror():
    with pytest.raises(LLMError) as e:
        GeminiLLM("", "m").generate_json("sys", [], {})
    assert "설정" in e.value.message_ko


def test_fake_llm_returns_in_order_and_records_calls():
    fake = FakeLLM([{"a": 1}, LLMError("x")])
    assert fake.generate_json("s", [("user", "hi")], {}) == {"a": 1}
    with pytest.raises(LLMError):
        fake.generate_json("s2", [], {})
    assert fake.calls[0] == ("s", [("user", "hi")], {})
