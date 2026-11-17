"""final_compare.py 테스트. 실행: python -m pytest analysis -q"""

from analysis.final_compare import audit_summary, cluster_bootstrap, draw_audit, half_of, voice_compare


def m(sid, date, words=5, corrected="False", voice="False", idx="1", **kw):
    base = {"session_id": sid, "date": date, "msg_idx": idx, "n_words": str(words), "text": "w " * words,
            "corrected": corrected, "via_voice": voice, "user_led": "False", "user_asked_question": "False",
            "n_mistakes": "0", "mode": "daily"}
    base.update(kw)
    return base


def test_half_of():
    assert [half_of(d) for d in ("2026-11-04", "2026-11-05", "2026-11-11", "2026-11-12")] == \
        ["", "first", "first", "second"]


def test_cluster_bootstrap_is_seeded_and_brackets_the_point_estimate():
    a = [m("a1", "2026-11-05", 10), m("a1", "2026-11-05", 12), m("a2", "2026-11-06", 8)]
    b = [m("b1", "2026-11-12", 4), m("b2", "2026-11-13", 6), m("b2", "2026-11-13", 5)]
    stat = lambda ms: sum(int(x["n_words"]) for x in ms) / len(ms)
    r1 = cluster_bootstrap(a, b, stat, n=300, seed=1)
    r2 = cluster_bootstrap(a, b, stat, n=300, seed=1)
    assert r1 == r2                                         # 같은 seed → 같은 결과
    assert r1["first"] == 10.0 and r1["second"] == 5.0 and r1["diff"] == -5.0
    assert r1["ci_low"] <= -5.0 <= r1["ci_high"] < 0          # 모든 재표본에서 후반부가 짧다


def test_voice_compare_drops_stt_mistakes():
    msgs = [m("s", "2026-11-13", 6, corrected="True", voice="True", idx="1"),
            m("s", "2026-11-13", 6, corrected="True", voice="True", idx="2"),
            m("s", "2026-11-13", 10, voice="False", idx="3")]
    mistakes = [{"session_id": "s", "msg_idx": "1", "valid": "True"}, {"session_id": "s", "msg_idx": "2", "valid": "True"},
                {"session_id": "s", "msg_idx": "2", "valid": "True"}]
    stt = {("s", "2")}      # 2번 메시지의 실수는 받아쓰기 오류
    rows = {r["input"]: r for r in voice_compare(msgs, mistakes, stt)}
    v = rows["voice"]
    assert (v["n_msgs"], v["mistakes"], v["stt_mistakes"], v["mistakes_per_msg_clean"]) == (2, 3, 2, 0.5)
    assert (v["corrected_rate"], v["corrected_rate_clean"]) == (1.0, 0.5)   # 2번은 받아쓰기 오류만 있어 교정 아님
    assert rows["typed"]["corrected_rate"] == 0.0


def test_draw_audit_is_stratified_and_reproducible():
    msgs = [m(f"s{i}", "2026-11-0" + ("5" if i < 20 else "4"), idx=str(i)) for i in range(25)] + \
           [m(f"t{i}", "2026-11-12", idx=str(i)) for i in range(20)]
    a = draw_audit(msgs, [], per_half=3, seed=7)
    assert [r["half"] for r in a].count("first") == 3 and [r["half"] for r in a].count("second") == 3
    assert all(r["date"] != "2026-11-04" for r in a)
    assert [r["session_id"] for r in a] == [r["session_id"] for r in draw_audit(msgs, [], per_half=3, seed=7)]
    assert [r["audit_id"] for r in a] == [1, 2, 3, 4, 5, 6]


def test_audit_summary_rates_per_half():
    rows = [{"half": "first", "ai_n_mistakes": "2", "h_false_mistakes": "1", "h_missed": "0", "ai_corrected": "True",
             "h_should_correct": "Y", "h_lead_ok": "Y", "h_question_ok": "Y"},
            {"half": "first", "ai_n_mistakes": "0", "h_false_mistakes": "0", "h_missed": "1", "ai_corrected": "False",
             "h_should_correct": "Y", "h_lead_ok": "N", "h_question_ok": "Y"}]
    s = {r["half"]: r for r in audit_summary(rows)}["first"]
    assert (s["n"], s["false_mistake_share"], s["missed_per_msg"]) == (2, 0.5, 0.5)
    assert (s["correct_agree"], s["lead_agree"], s["question_agree"]) == (0.5, 0.5, 1.0)
