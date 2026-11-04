"""대화 엔진: AI 첫 마디, 턴 주고받기, 세션 저장."""

import threading
from datetime import date, datetime

from talk.llm import BROKEN_MSG, LLM, LLMError
from talk.models import Correction, DayPlan, Message, Mistake, Session, TurnResult
from talk.prompts import OPENING_SCHEMA, TURN_SCHEMA, build_system_prompt, opening_instruction
from talk.store import Store, new_session_id

LONG_ABSENCE_DAYS = 3
VOICE_HINT = "\n[This message came from speech recognition and may contain recognition errors.]"
SAVE_EVERY_SECONDS = 30


def _parse_turn(data: dict) -> TurnResult:
    reply = data.get("reply")
    if not isinstance(reply, str) or not reply.strip():
        raise LLMError(BROKEN_MSG)
    try:
        corr = data.get("correction")
        return TurnResult(
            reply=reply.strip(),
            reply_ko=data.get("reply_ko") or None,
            correction=Correction(corr["native"], corr["why_ko"], corr.get("extend") or None) if corr else None,
            help_ko=data.get("help_ko") or None,
            help_expr=data.get("help_expr") or None,
            user_asked_question=bool(data.get("user_asked_question")),
            user_led=bool(data.get("user_led")),
            mistakes=[Mistake(m["key"], m["original"], m["native"], m["area"], bool(m.get("voice_sensitive")))
                      for m in data.get("mistakes") or []],
            targets_used_correctly=[str(k) for k in data.get("targets_used_correctly") or []],
        )
    except (KeyError, TypeError) as exc:
        raise LLMError(BROKEN_MSG) from exc


class Conversation:
    def __init__(self, llm: LLM, store: Store, plan: DayPlan, mode: str, memory: dict, now=datetime.now,
                 level: float = 1.0):
        self.level = level
        self.llm, self.store, self.plan, self.mode, self.memory, self.now = llm, store, plan, mode, memory, now
        started = now()
        self.session = Session(
            id=new_session_id(started), date=started.date().isoformat(), mode=mode,
            topic=plan.topics.get(mode, ""), style=plan.style, started=started.isoformat(timespec="seconds"),
            seconds=0,
        )
        self.discarded = False
        self._lock = threading.Lock()

    def discard(self) -> None:
        """버려진 대화. 늦게 도착한 AI 답장이 세션 파일을 다시 만들지 않게 한다."""
        self.discarded = True

    def _system(self) -> str:
        return build_system_prompt(self.mode, self.plan, self.memory, self._question_streak(), self.level)

    def _question_streak(self) -> int:
        n = 0
        for m in reversed([m for m in self.session.messages if m.role == "ai"]):
            if not m.text.rstrip().endswith("?"):
                break
            n += 1
        return n

    def _history(self) -> list[tuple[str, str]]:
        out = []
        for m in self.session.messages:
            text = m.text + (VOICE_HINT if m.via_voice else "")
            out.append(("model" if m.role == "ai" else "user", text))
        return out

    def _absence_days(self) -> int | None:
        past = [s for s in self.store.list_sessions() if s.id != self.session.id and s.messages]
        if not past:
            return None
        days = (date.fromisoformat(self.session.date) - date.fromisoformat(past[-1].date)).days
        return days if days > LONG_ABSENCE_DAYS else None

    def opening(self) -> str:
        system = self._system() + "\n\n" + opening_instruction(self._absence_days(), self.plan.style)
        data = self.llm.generate_json(system, [], OPENING_SCHEMA)
        text = data.get("reply")
        if not isinstance(text, str) or not text.strip():
            raise LLMError(BROKEN_MSG)
        with self._lock:
            if self.discarded:
                return text.strip()
            self.session.messages.append(Message("ai", text.strip(), self._ts(),
                                                 translation_ko=data.get("reply_ko") or None))
            self.store.save_session(self.session)
        return text.strip()

    def send(self, text: str, via_voice: bool = False) -> TurnResult:
        user = Message("user", text, self._ts(), via_voice=via_voice)
        history = self._history() + [("user", text + (VOICE_HINT if via_voice else ""))]
        result = _parse_turn(self.llm.generate_json(self._system(), history, TURN_SCHEMA))
        user.correction, user.help_ko = result.correction, result.help_ko
        with self._lock:
            if self.discarded:
                return result
            self.session.messages += [user, Message("ai", result.reply, self._ts(), translation_ko=result.reply_ko)]
            self.session.turns.append(result)
            self.store.save_session(self.session)
        return result

    def add_seconds(self, n: int) -> None:
        with self._lock:
            self.session.seconds += n
            if self.session.seconds % SAVE_EVERY_SECONDS < n and not self.discarded:
                self.store.save_session(self.session)

    def _ts(self) -> str:
        return self.now().isoformat(timespec="seconds")
