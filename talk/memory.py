"""기억: 대화가 끝나면 실수, 주제 요약, 사용자 정보를 정리해 memory.json에 쌓는다."""

from dataclasses import asdict, dataclass, field

from talk.llm import LLM, LLMError
from talk.models import Session
from talk.store import Store

MAX_TOPICS = 30
MAX_FACTS = 50
MAX_PROCESSED = 500

SUMMARY_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "topic_summary": {"type": "STRING"},
        "new_facts": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["topic_summary", "new_facts"],
}

SUMMARY_PROMPT = (
    "Summarize this English practice conversation for your own memory. topic_summary: one or two English "
    "sentences about what was talked about, so you can continue it another day. new_facts: short English facts "
    "about the user (job, hobbies, plans, people in their life) that are new compared to: {facts}"
)


@dataclass
class SessionOutcome:
    repeated: list[dict] = field(default_factory=list)
    now_correct: list[dict] = field(default_factory=list)
    learned: list[dict] = field(default_factory=list)


def load_memory(store: Store) -> dict:
    mem = store.load_json("memory.json", {})
    if not isinstance(mem, dict):
        mem = {}
    mem.setdefault("topics", [])
    mem.setdefault("mistakes", {})
    mem.setdefault("facts", [])
    mem.setdefault("processed", [])
    return mem


def _learned(session: Session) -> list[dict]:
    users = [m for m in session.messages if m.role == "user"]
    out = []
    for msg, turn in zip(users, session.turns):
        if turn.correction:
            out.append({"original": msg.text, "native": turn.correction.native, "why_ko": turn.correction.why_ko})
        if turn.help_ko and turn.help_expr:
            out.append({"original": msg.text, "native": turn.help_expr, "why_ko": turn.help_ko})
    return out


def finish_session(llm: LLM, store: Store, session: Session) -> SessionOutcome:
    """기억을 갱신하고 결과를 돌려준다. 같은 세션으로 다시 불러도 두 번 쌓이지 않는다.
    finished 표시는 일일 리포트까지 쓴 뒤 reports.finalize_session이 한다."""
    if session.finished:
        return SessionOutcome()
    mem = load_memory(store)
    if session.id in mem["processed"]:
        saved = store.load_json(f"outcomes/{session.id}.json", None)
        return SessionOutcome(**saved) if saved else SessionOutcome()
    mistakes = mem["mistakes"]
    today = session.date
    before = {k for k, m in mistakes.items() if m.get("last_seen", "") < today}

    repeated: dict[str, dict] = {}
    for turn in session.turns:
        for m in turn.mistakes:
            if m.voice_sensitive:
                continue
            entry = mistakes.get(m.key)
            if entry is None:
                entry = mistakes[m.key] = {"original": m.original, "native": m.native, "area": m.area, "count": 0,
                                           "first_seen": today, "last_seen": today, "last_correct": None,
                                           "voice_only": False}
            entry["count"] += 1
            entry["last_seen"] = today
            entry["original"], entry["native"] = m.original, m.native
            if m.key in before:
                repeated[m.key] = {"key": m.key, "original": m.original, "native": m.native,
                                   "count": entry["count"], "first_seen": entry["first_seen"]}

    now_correct: dict[str, dict] = {}
    for turn in session.turns:
        for key in turn.targets_used_correctly:
            if key in mistakes:
                mistakes[key]["last_correct"] = today
                now_correct[key] = {"key": key, "native": mistakes[key]["native"]}

    summary, facts = session.topic, []
    try:
        history = [("model" if m.role == "ai" else "user", m.text) for m in session.messages]
        data = llm.generate_json(SUMMARY_PROMPT.format(facts="; ".join(mem["facts"]) or "(none)"),
                                 history, SUMMARY_SCHEMA)
        summary = str(data.get("topic_summary") or session.topic)
        facts = [str(f) for f in data.get("new_facts") or []]
    except LLMError:
        pass

    mem["topics"] = ([{"date": today, "mode": session.mode, "topic": session.topic, "summary": summary}]
                     + mem["topics"])[:MAX_TOPICS]
    mem["facts"] = (mem["facts"] + [f for f in facts if f not in mem["facts"]])[-MAX_FACTS:]
    mem["processed"] = (mem["processed"] + [session.id])[-MAX_PROCESSED:]
    outcome = SessionOutcome(list(repeated.values()), list(now_correct.values()), _learned(session))
    # 결과를 먼저 남기고 기억을 저장한다. 그 사이에 꺼지면 다음에 처음부터 다시 계산한다
    store.save_json(f"outcomes/{session.id}.json", asdict(outcome))
    store.save_json("memory.json", mem)
    return outcome
