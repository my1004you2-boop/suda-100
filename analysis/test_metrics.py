"""metrics.py 테스트. 실행: python -m pytest analysis -q"""

from analysis.metrics import daily_metrics, ttr


def test_ttr_uses_fixed_length():
    words = ["a", "b", "a", "c"] * 50                 # 200단어, 서로 다른 단어 3개
    assert ttr(words, n=150) == round(3 / 150, 3)
    assert ttr(["a", "b"], n=150) == ""               # 150단어가 안 되면 계산하지 않는다


def _msg(date, text, words, **kw):
    base = {"date": date, "text": text, "n_words": str(words), "has_korean": "False", "asked_help_ko": "False",
            "corrected": "False", "user_led": "False", "user_asked_question": "False", "via_voice": "False",
            "session_id": f"{date}-s"}
    base.update({k: str(v) for k, v in kw.items()})
    return base


def test_daily_metrics():
    sessions = [{"date": "2026-11-05", "session_id": "s1", "minutes": "10.0"},
                {"date": "2026-11-05", "session_id": "s2", "minutes": "2.0"}]
    messages = [_msg("2026-11-05", "i like it", 3, corrected=True, user_led=True),
                _msg("2026-11-05", "do you 좋아해 it", 3, has_korean=True, user_asked_question=True, via_voice=True),
                _msg("2026-11-05", "ok", 1)]
    mistakes = [{"date": "2026-11-05", "valid": "True", "mistake_id": "x", "repeat": "False"},
                {"date": "2026-11-05", "valid": "True", "mistake_id": "y", "repeat": "True"},
                {"date": "2026-11-05", "valid": "False", "mistake_id": "z", "repeat": ""}]
    row = daily_metrics(sessions, messages, mistakes)[0]
    assert row["date"] == "2026-11-05" and row["n_sessions"] == 2 and row["minutes"] == 12.0
    assert row["n_msgs"] == 3 and row["avg_words"] == round(7 / 3, 1) and row["median_words"] == 3
    assert row["corrected_rate"] == round(1 / 3, 3) and row["korean_rate"] == round(1 / 3, 3)
    assert row["lead_rate"] == round(2 / 3, 3) and row["question_rate"] == round(1 / 3, 3)
    assert row["voice_rate"] == round(1 / 3, 3)
    assert row["mistakes_per_msg"] == round(2 / 3, 2)        # 유효한 실수만
    assert row["n_mistakes"] == 2 and row["n_repeat"] == 1 and row["repeat_rate"] == 0.5
