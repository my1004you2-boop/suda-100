"""prep.py 테스트. 실행: python -m pytest analysis -q"""

import csv
import json

from analysis.prep import count_words, day_n, has_korean, run, work_day


def _session(sid, date, user_texts, turns, **kw):
    msgs = [{"role": "ai", "text": "Hi!", "ts": f"{date}T10:00:00", "via_voice": False}]
    for i, t in enumerate(user_texts):
        msgs.append({"role": "user", "text": t, "ts": f"{date}T10:0{i + 1}:00", "via_voice": i == 0,
                     "correction": {"native": "x", "why_ko": "y"} if i == 0 else None,
                     "help_ko": "도움" if "한국" in t else None})
        msgs.append({"role": "ai", "text": "ok", "ts": f"{date}T10:0{i + 1}:30", "via_voice": False})
    base = {"id": sid, "date": date, "mode": "daily", "topic": "주제", "style": "ai_story",
            "started": f"{date}T10:00:00", "seconds": 600, "messages": msgs, "turns": turns,
            "finished": True}
    base.update(kw)
    return base


def _turn(led=False, q=False, n_mistakes=0):
    return {"reply": "ok", "user_led": led, "user_asked_question": q,
            "mistakes": [{"key": "k", "original": "o", "native": "n", "area": "grammar"}] * n_mistakes}


def _write(tmp_path, *sessions):
    d = tmp_path / "data" / "sessions"
    d.mkdir(parents=True)
    for s in sessions:
        (d / f"{s['id']}.json").write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    return tmp_path / "data", tmp_path / "out"


def _read(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def test_helpers():
    assert count_words("i don't have long sleep.") == 5
    assert count_words("I want to 예약 변경 for 2 days") == 5
    assert has_korean("I want 예약") and not has_korean("hello")
    assert day_n("2026-11-04") == 0 and day_n("2026-11-05") == 1 and day_n("2026-11-18") == 14
    assert work_day("2026-11-05") == 1 and work_day("2026-11-09") == 3 and work_day("2026-11-18") == 10
    assert work_day("2026-11-07") is None and work_day("2026-11-04") is None


def test_run_builds_sessions_and_messages(tmp_path):
    s = _session("20261105-100000", "2026-11-05", ["i like it", "한국말 섞인 why need more time?"],
                 [_turn(led=True), _turn(q=True, n_mistakes=2)], model="m", prompt_version="v")
    data, out = _write(tmp_path, s)
    warnings = run(data, out)

    sessions = _read(out / "sessions.csv")
    assert len(sessions) == 1
    row = sessions[0]
    assert row["day_n"] == "1" and row["work_day"] == "1" and row["minutes"] == "10.0"
    assert row["n_user_msgs"] == "2" and row["voice_ratio"] == "0.5" and row["turns_match"] == "True"
    assert row["model"] == "m" and row["prompt_version"] == "v"

    msgs = _read(out / "messages.csv")
    assert [m["msg_idx"] for m in msgs] == ["1", "2"]
    assert msgs[0]["corrected"] == "True" and msgs[0]["user_led"] == "True" and msgs[0]["via_voice"] == "True"
    assert msgs[1]["has_korean"] == "True" and msgs[1]["asked_help_ko"] == "True"
    assert msgs[1]["user_asked_question"] == "True" and msgs[1]["n_mistakes"] == "2"
    assert warnings == []


def test_mismatch_and_short_session_warned(tmp_path):
    bad = _session("20261105-110000", "2026-11-05", ["a", "b"], [_turn()], seconds=100)
    old = _session("20261104-090000", "2026-11-04", ["hi"], [_turn()])   # 11/4 옛 형식: model 없음
    data, out = _write(tmp_path, bad, old)
    warnings = run(data, out)

    msgs = _read(out / "messages.csv")
    second = [m for m in msgs if m["session_id"] == "20261105-110000"][1]
    assert second["user_led"] == "" and second["n_mistakes"] == ""      # 짝이 없는 턴은 빈칸
    assert any("턴 수 불일치" in w for w in warnings)
    assert any("3분 미만" in w for w in warnings)
    rows = {r["session_id"]: r for r in _read(out / "sessions.csv")}
    assert rows["20261104-090000"]["prompt_version"] == "" and rows["20261104-090000"]["work_day"] == ""
    assert (out / "warnings.txt").exists()


def test_run_is_idempotent(tmp_path):
    data, out = _write(tmp_path, _session("20261105-100000", "2026-11-05", ["hi"], [_turn()]))
    run(data, out)
    first = (out / "messages.csv").read_bytes()
    run(data, out)
    assert (out / "messages.csv").read_bytes() == first
