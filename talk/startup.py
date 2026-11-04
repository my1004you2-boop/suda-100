"""앱을 켤 때 하는 일: 마무리 안 된 대화 정리, 밀린 주간 평가서 작성."""

import traceback
from datetime import date, timedelta

from talk.config import Settings
from talk.llm import LLM, LLMError
from talk.planner import week_id
from talk.reports import build_weekly, finalize_session, week_sessions
from talk.store import Store

CATCH_UP_WEEKS = 4


def run_startup(llm: LLM, store: Store, settings: Settings, active_id: str | None, today: date) -> bool:
    """마무리 안 된 대화를 정리하고, 최근 몇 주 중 평가서가 없는 주를 쓴다. 새 평가서를 썼으면 True."""
    changed = False
    for s in store.unfinished_sessions():
        if s.id == active_id:
            continue
        if not any(m.role == "user" for m in s.messages):
            store.delete_session(s.id)
            continue
        try:
            finalize_session(llm, store, s)
            changed = True
        except Exception:
            traceback.print_exc()  # 이 대화는 다음 실행에 다시 시도하고, 나머지는 계속 정리한다

    built = False
    weeks = dict.fromkeys(week_id(today - timedelta(days=7 * i)) for i in range(CATCH_UP_WEEKS, 0, -1))
    for week in weeks:  # 오래된 주부터: 다음 주 평가가 지난주 점수를 참고한다
        if store.load_json(f"weekly/{week}.json", None) is not None or not week_sessions(store, week):
            continue
        try:
            build_weekly(llm, store, week, settings)
            built = True
        except LLMError:
            break  # 다음에 앱을 켤 때 다시 시도

    if (changed or built) and not any(s.messages for s in store.list_sessions(today.isoformat())):
        # 오늘 대화를 아직 안 했다면, 새 기억과 평가서를 반영하도록 오늘 계획을 다시 만든다
        (store.root / "plans" / f"{today.isoformat()}.json").unlink(missing_ok=True)
    return built
