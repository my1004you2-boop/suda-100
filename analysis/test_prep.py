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
    warnings = run(data, out, tmp_path / "map.csv")

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
    assert not any("불일치" in w or "3분 미만" in w for w in warnings)


def test_mismatch_and_short_session_warned(tmp_path):
    bad = _session("20261105-110000", "2026-11-05", ["a", "b"], [_turn()], seconds=100)
    old = _session("20261104-090000", "2026-11-04", ["hi"], [_turn()])   # 11/4 옛 형식: model 없음
    data, out = _write(tmp_path, bad, old)
    warnings = run(data, out, tmp_path / "map.csv")

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
    run(data, out, tmp_path / "map.csv")
    first = (out / "messages.csv").read_bytes()
    run(data, out, tmp_path / "map.csv")
    assert (out / "messages.csv").read_bytes() == first


# --- 3일차: 실수 표, 숨은 연습 표, 실수 ID 매핑, 품질 점검 ---

def _m(original, native="n", key="k", area="grammar"):
    return {"key": key, "original": original, "native": native, "area": area}


def _turn_m(*mistakes, used=()):
    return {"reply": "ok", "user_led": False, "user_asked_question": False, "mistakes": list(mistakes),
            "targets_used_correctly": list(used)}


def test_quality_helpers():
    from analysis.prep import in_text, norm
    assert norm("  Why  need more time?? ") == "why need more time"
    assert in_text("why need more time", "ok. Why need more time? i heared")
    assert in_text("i heared you", "Why need more time? I heared  you finished")   # 띄어쓰기·대소문자 무시
    assert not in_text("so so", "Do you have a help?")


def test_mistakes_csv_flags_and_mapping(tmp_path):
    from analysis.prep import read_map
    s1 = _session("20261105-100000", "2026-11-05", ["i drinked tea", "Do you have a help?"],
                  [_turn_m(_m("drinked", "drank"), _m("drinked", "drank")),        # 한 메시지 안 중복
                   _turn_m(_m("so so", "It was so-so."))])                          # 말하지 않은 실수
    s2 = _session("20261106-100000", "2026-11-06", ["i drinked coffee"], [_turn_m(_m("drinked", "drank"))])
    data, out = _write(tmp_path, s1, s2)
    map_path = tmp_path / "mistake_map.csv"
    run(data, out, map_path)

    # 처음 실행: 매핑표에 빈 ID로 추가된다 (같은 원문·교정문은 한 줄)
    rows = read_map(map_path)
    assert [(r["original"], r["native"], r["mistake_id"]) for r in rows] == [
        ("drinked", "drank", ""), ("so so", "It was so-so.", "")]

    # 사람이 ID를 채운 뒤 다시 실행
    rows[0]["mistake_id"] = "past_irregular_drink"
    from analysis.prep import write_map
    write_map(map_path, rows)
    warnings = run(data, out, map_path)

    ms = _read(out / "mistakes.csv")
    assert len(ms) == 4
    assert [m["dup_in_msg"] for m in ms] == ["False", "True", "False", "False"]
    assert [m["not_in_text"] for m in ms] == ["False", "False", "True", "False"]
    assert [m["mistake_id"] for m in ms] == ["past_irregular_drink"] * 2 + ["", "past_irregular_drink"]
    # 재발: 이전 날짜에 같은 ID가 있었는지 (중복·가짜 기록은 세지 않음)
    assert [m["repeat"] for m in ms] == ["False", "", "", "True"]
    assert len(read_map(map_path)) == 2                                   # 다시 돌려도 매핑표가 늘지 않음
    assert any("말하지 않은 실수" in w for w in warnings)
    assert any("ID 없는 실수" in w for w in warnings)


def test_practice_csv(tmp_path):
    s = _session("20261106-100000", "2026-11-06", ["a", "b"],
                 [_turn_m(used=["t1"]), _turn_m(_m("b", key="t2"))])
    data, out = _write(tmp_path, s)
    (data / "plans").mkdir()
    (data / "plans" / "2026-11-06.json").write_text(json.dumps({"date": "2026-11-06", "targets": ["t1", "t2", "t3"]}),
                                                    encoding="utf-8")
    run(data, out, tmp_path / "map.csv")
    rows = {r["key"]: r for r in _read(out / "practice.csv")}
    assert rows["t1"]["used_correctly"] == "True" and rows["t1"]["mistaken_again"] == "False"
    assert rows["t2"]["used_correctly"] == "False" and rows["t2"]["mistaken_again"] == "True"
    assert rows["t3"]["n_sessions"] == "1" and rows["t3"]["used_correctly"] == "False"


def test_no_change_mistake_is_invalid_and_not_mapped(tmp_path):
    from analysis.prep import read_map
    s = _session("20261112-100000", "2026-11-12", ["there are no such lyrics", "i drinked tea"],
                 [_turn_m(_m("no such lyrics", "No such lyrics.")),                 # 틀린 말 = 맞는 말
                  _turn_m(_m("drinked", "drank"))])
    data, out = _write(tmp_path, s)
    map_path = tmp_path / "mistake_map.csv"
    warnings = run(data, out, map_path)
    ms = _read(out / "mistakes.csv")
    assert [m["no_change"] for m in ms] == ["True", "False"]
    assert [m["valid"] for m in ms] == ["False", "True"]
    assert [r["original"] for r in read_map(map_path)] == ["drinked"]          # ID를 붙일 필요가 없다
    assert any("고칠 것 없는 실수 기록" in w for w in warnings)
