"""interim.py 테스트. 실행: python -m pytest analysis -q"""

from analysis.interim import by_group, cumulative_recurrence, wilson


def _mk(date, mid, valid="True", repeat="False", sid="s1"):
    return {"date": date, "mistake_id": mid, "valid": valid, "repeat": repeat, "session_id": sid}


def test_cumulative_recurrence_counts_ids_seen_on_two_or_more_days():
    rows = [_mk("2026-11-05", "a"), _mk("2026-11-05", "b"), _mk("2026-11-05", "b"),   # 같은 날 두 번은 1일
            _mk("2026-11-06", "a"), _mk("2026-11-06", "c"),
            _mk("2026-11-06", "d", valid="False"), _mk("2026-11-06", "")]              # 무효·ID 없음 제외
    out = cumulative_recurrence(rows)
    assert [(r["date"], r["n_ids"], r["n_multi_day"]) for r in out] == [("2026-11-05", 2, 0), ("2026-11-06", 3, 1)]
    assert out[1]["cum_recurrence"] == round(1 / 3, 3)


def test_wilson_interval():
    lo, hi = wilson(4, 10)
    assert lo < 0.4 < hi and round(lo, 2) == 0.17 and round(hi, 2) == 0.69
    assert wilson(0, 0) == (0.0, 1.0)
    assert wilson(0, 5)[0] == 0.0 and wilson(5, 5)[1] == 1.0


def test_by_group_splits_by_session_mode_and_drops_short_sessions_from_count():
    sessions = [{"session_id": "s1", "date": "2026-11-05", "mode": "daily", "minutes": "10.0"},
                {"session_id": "s2", "date": "2026-11-06", "mode": "verb", "minutes": "1.0"}]
    base = {"has_korean": "False", "asked_help_ko": "False", "user_led": "False", "user_asked_question": "False",
            "via_voice": "False"}
    messages = [dict(base, session_id="s1", date="2026-11-05", text="i like it", n_words="3", corrected="True"),
                dict(base, session_id="s2", date="2026-11-06", text="go", n_words="1", corrected="False")]
    rows = {r["group"]: r for r in by_group(sessions, messages, [_mk("2026-11-05", "a")], "mode")}
    assert rows["daily"]["n_sessions"] == 1 and rows["daily"]["corrected_rate"] == 1.0
    assert rows["daily"]["n_mistakes"] == 1 and rows["daily"]["dates"] == "11-05"
    assert rows["verb"]["n_sessions"] == 0 and rows["verb"]["n_msgs"] == 1   # 짧은 대화도 메시지는 남긴다


def test_by_group_since_drops_earlier_dates():
    sessions = [{"session_id": "s0", "date": "2026-11-04", "mode": "daily", "minutes": "10.0"},
                {"session_id": "s1", "date": "2026-11-05", "mode": "daily", "minutes": "10.0"}]
    base = {"has_korean": "False", "asked_help_ko": "False", "user_led": "False", "user_asked_question": "False",
            "via_voice": "False", "text": "hi", "n_words": "1"}
    messages = [dict(base, session_id="s0", date="2026-11-04", corrected="True"),
                dict(base, session_id="s1", date="2026-11-05", corrected="False")]
    row = by_group(sessions, messages, [], "mode", since="2026-11-05")[0]
    assert row["n_msgs"] == 1 and row["corrected_rate"] == 0.0 and row["dates"] == "11-05"
