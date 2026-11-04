"""대화 AI 호출. 앱은 LLM 프로토콜만 알고, 실제 회사(Gemini 등)는 여기서만 다룬다."""

import json
import time
from typing import Protocol

RETRY_WAITS = [2, 5, 10]
TIMEOUT_MS = 30_000
BUSY_MSG = "AI가 잠시 바빠요. 잠시 후 다시 시도해 주세요."
BROKEN_MSG = "AI 답장을 읽지 못했어요. 잠시 후 다시 시도해 주세요."
REJECTED_MSG = "AI에 연결하지 못했어요. 설정의 API 키와 모델 이름을 확인해 주세요."
NO_KEY_MSG ="설정에서 Gemini API 키를 먼저 넣어 주세요."


class LLMError(Exception):
    def __init__(self, message_ko: str):
        super().__init__(message_ko)
        self.message_ko = message_ko


class LLM(Protocol):
    def generate_json(self, system: str, history: list[tuple[str, str]], schema: dict) -> dict: ...


def _is_retryable(exc: Exception) -> bool:
    from google.genai import errors

    if isinstance(exc, errors.APIError):
        return exc.code == 429 or exc.code >= 500
    try:
        import httpx
        if isinstance(exc, httpx.TransportError):
            return True
    except ImportError:
        pass
    return isinstance(exc, (ConnectionError, TimeoutError))


class GeminiLLM:
    def __init__(self, api_key: str, model: str, sleep=time.sleep):
        self.api_key = api_key
        self.model = model
        self.sleep = sleep
        self._client = None

    def _http_options(self):
        from google.genai import types

        return types.HttpOptions(timeout=TIMEOUT_MS)  # 기본값은 무한 대기

    def _call(self, system: str, history: list[tuple[str, str]], schema: dict) -> str:
        from google import genai
        from google.genai import types

        if self._client is None:
            self._client = genai.Client(api_key=self.api_key, http_options=self._http_options())
        # Gemini는 대화가 user 차례로 시작해야 한다
        if not history or history[0][0] != "user":
            history = [("user", "(conversation starts)")] + list(history)
        contents = [types.Content(role=role, parts=[types.Part(text=text)]) for role, text in history]
        resp = self._client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_schema=schema or None,
            ),
        )
        return resp.text or ""

    def generate_json(self, system: str, history: list[tuple[str, str]], schema: dict) -> dict:
        if not self.api_key:
            raise LLMError(NO_KEY_MSG)
        for attempt in range(len(RETRY_WAITS) + 1):
            try:
                text = self._call(system, history, schema)
                break
            except Exception as exc:
                if not _is_retryable(exc):
                    raise LLMError(REJECTED_MSG) from exc
                if attempt == len(RETRY_WAITS):
                    raise LLMError(BUSY_MSG) from exc
                self.sleep(RETRY_WAITS[attempt])
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise LLMError(BROKEN_MSG) from exc
        if not isinstance(data, dict):
            raise LLMError(BROKEN_MSG)
        return data


class FakeLLM:
    """테스트용. 정해 둔 응답을 차례로 돌려준다."""

    def __init__(self, responses: list):
        self.responses = list(responses)
        self.calls: list[tuple] = []

    def generate_json(self, system: str, history: list[tuple[str, str]], schema: dict) -> dict:
        self.calls.append((system, list(history), schema))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
