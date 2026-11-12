"""balance.py 테스트. 실행: python -m pytest analysis -q"""

from analysis.balance import first_half_ids, freeze, mode_balance, style_dates


def _s(sid, date, mode, minutes="10.0", style="ai_story"):
    return {"session_id": sid, "date": date, "mode": mode, "minutes": minutes, "style": style}


def test_mode_balance_splits_halves_and_skips_short_and_baseline():
    sessions = [_s("a", "2026-11-04", "verb"),                    # 기준일: 제외
                _s("b", "2026-11-05", "verb"), _s("c", "2026-11-06", "verb", minutes="1.0"),  # 짧은 대화: 제외
                _s("d", "2026-11-12", "verb")]
    messages = [{"session_id": "b", "date": "2026-11-05"}, {"session_id": "d", "date": "2026-11-12"},
                {"session_id": "d", "date": "2026-11-12"}]
    verb = {r["mode"]: r for r in mode_balance(sessions, messages)}["verb"]
    assert (verb["sessions_first"], verb["sessions_second"], verb["sessions_total"]) == (1, 1, 2)
    assert (verb["msgs_first"], verb["msgs_second"]) == (1, 2)
    assert verb["short_of_target"] == 2


def test_style_dates_unique_and_ordered():
    sessions = [_s("a", "2026-11-11", "daily", style="goal_roleplay"),
                _s("b", "2026-11-05", "daily", style="goal_roleplay"),
                _s("c", "2026-11-05", "verb", style="goal_roleplay")]
    assert style_dates(sessions) == {"goal_roleplay": ["2026-11-05", "2026-11-11"]}


def test_first_half_ids_and_freeze_once(tmp_path):
    def mk(date, mid, valid="True"):
        return {"date": date, "mistake_id": mid, "valid": valid}

    rows = first_half_ids([mk("2026-11-05", "a"), mk("2026-11-09", "a"), mk("2026-11-09", "a"),
                           mk("2026-11-06", "b"), mk("2026-11-06", "c", valid="False"),
                           mk("2026-11-06", ""), mk("2026-11-12", "d")])          # 후반부: 제외
    assert [(r["mistake_id"], r["n_days"], r["n_records"], r["first_date"], r["last_date"]) for r in rows] == [
        ("a", 2, 3, "2026-11-05", "2026-11-09"), ("b", 1, 1, "2026-11-06", "2026-11-06")]
    path = tmp_path / "first_half_ids.csv"
    assert freeze(rows, path) is True
    assert freeze(rows[:1], path) is False                                        # 두 번째는 덮어쓰지 않는다
    assert path.read_text(encoding="utf-8-sig").count("\n") == 3
    assert freeze(rows[:1], path, force=True) is True
