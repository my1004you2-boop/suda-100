"""speech_change.py 테스트. 실행: python -m pytest analysis -q"""

from analysis.speech_change import (bucket_of, corrected_by_length, length_profile, msttr, standardized_rate,
                                    style_pairs)


def msg(date, n_words, text="", corrected="False", sid="s1", **kw):
    base = {"date": date, "session_id": sid, "n_words": str(n_words), "text": text or " ".join(["w"] * n_words),
            "corrected": corrected, "has_korean": "False", "asked_help_ko": "False", "user_led": "False",
            "user_asked_question": "False", "via_voice": "False", "n_mistakes": "0"}
    base.update(kw)
    return base


def test_length_profile_median_quartiles_and_short_long_shares():
    ms = [msg("2026-11-05", n) for n in (1, 2, 5, 8, 12)] + [msg("2026-11-06", 4)]
    p = {r["date"]: r for r in length_profile(ms)}
    d = p["2026-11-05"]
    assert (d["n_msgs"], d["median"], d["q1"], d["q3"]) == (5, 5, 1.5, 10)   # 아래 절반 [1,2], 위 절반 [8,12]
    assert (d["short_share"], d["long_share"]) == (0.4, 0.2)   # 3단어 이하 2개, 10단어 이상 1개
    assert p["2026-11-06"]["median"] == 4


def test_msttr_averages_full_chunks_and_drops_remainder():
    words = ["a"] * 50 + [f"w{i}" for i in range(50)] + ["x"] * 10
    assert msttr(words, size=50) == (0.51, 2)          # (1/50 + 50/50) / 2, 남은 10단어는 버림
    assert msttr(["a"] * 49, size=50) == ("", 0)


def test_bucket_of():
    assert [bucket_of(n) for n in (1, 4, 5, 9, 10, 30)] == ["1-4", "1-4", "5-9", "5-9", "10+", "10+"]


def test_corrected_by_length_groups_by_key_and_bucket():
    ms = [msg("2026-11-05", 2, corrected="True"), msg("2026-11-05", 3), msg("2026-11-05", 12, corrected="True"),
          msg("2026-11-12", 12)]
    rows = {(r["group"], r["bucket"]): r for r in corrected_by_length(ms, key=lambda m: m["date"][5:])}
    assert (rows[("11-05", "1-4")]["n"], rows[("11-05", "1-4")]["corrected_rate"]) == (2, 0.5)
    assert rows[("11-05", "10+")]["corrected_rate"] == 1.0
    assert rows[("11-12", "10+")]["corrected_rate"] == 0.0
    assert ("11-12", "1-4") not in rows


def test_style_pairs_reports_each_date_in_pair():
    sessions = [{"session_id": "a", "date": "2026-11-05", "style": "goal_roleplay", "minutes": "10"},
                {"session_id": "b", "date": "2026-11-11", "style": "goal_roleplay", "minutes": "10"},
                {"session_id": "c", "date": "2026-11-06", "style": "ai_story", "minutes": "10"}]
    ms = [msg("2026-11-05", 4, sid="a", user_led="True"), msg("2026-11-05", 10, sid="a"),
          msg("2026-11-11", 12, sid="b", user_asked_question="True")]
    rows = style_pairs(sessions, ms, [])
    assert [(r["style"], r["date"]) for r in rows] == [("goal_roleplay", "2026-11-05"), ("goal_roleplay", "2026-11-11")]
    assert rows[0]["avg_words"] == 7.0 and rows[0]["lead_rate"] == 0.5
    assert rows[1]["median_words"] == 12 and rows[1]["question_rate"] == 1.0


def test_standardized_rate_reweights_by_reference_length_mix():
    rows = [{"group": "A", "bucket": "1-4", "n": 10, "corrected_rate": 0.2},
            {"group": "A", "bucket": "10+", "n": 30, "corrected_rate": 0.8},
            {"group": "B", "bucket": "1-4", "n": 30, "corrected_rate": 0.1},
            {"group": "B", "bucket": "10+", "n": 10, "corrected_rate": 0.5}]
    assert standardized_rate(rows, "B", "A") == 0.4      # (0.1*10 + 0.5*30) / 40
    assert standardized_rate(rows, "A", "A") == 0.65
