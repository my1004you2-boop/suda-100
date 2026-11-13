"""mistake_repeat.py 테스트. 실행: python -m pytest analysis -q"""

from analysis.mistake_repeat import id_types, kaplan_meier, reappearance, recurrence_by_type, survival_rows


def mk(date, mid, area="grammar", valid="True"):
    return {"date": date, "mistake_id": mid, "area": area, "valid": valid}


FROZEN = [{"mistake_id": "a", "n_days": "2"}, {"mistake_id": "b", "n_days": "1"},
          {"mistake_id": "c", "n_days": "1"}]


def test_reappearance_counts_frozen_ids_seen_in_second_half_by_group():
    mistakes = [mk("2026-11-12", "a"), mk("2026-11-13", "a"), mk("2026-11-13", "b"),
                mk("2026-11-13", "c", valid="False"),   # 무효 기록은 재등장으로 세지 않는다
                mk("2026-11-12", "z"),                  # 전반부에 없던 새 ID: 분모 밖
                mk("2026-11-10", "c")]                  # 전반부 기록: 재등장 아님
    rows = {r["group"]: r for r in reappearance(FROZEN, mistakes, since="2026-11-12")}
    assert (rows["all"]["k"], rows["all"]["n"], rows["all"]["rate"]) == (2, 3, 0.667)
    assert (rows["multi_day"]["k"], rows["multi_day"]["n"]) == (1, 1)
    assert (rows["single_day"]["k"], rows["single_day"]["n"]) == (1, 2)
    assert rows["all"]["ids"] == "a b"
    assert 0 <= rows["all"]["ci_low"] < 0.667 < rows["all"]["ci_high"] <= 1


def test_id_types_normalizes_area_and_spelling_suffix_and_grammar_group():
    mistakes = [mk("2026-11-04", "x_spelling", area="grammar"), mk("2026-11-04", "deadline", area="어휘 선택"),
                mk("2026-11-05", "deadline", area="expression"), mk("2026-11-05", "deadline", area="Vocabulary"),
                mk("2026-11-04", "flow", area="phrasal_flow"), mk("2026-11-05", "question_word_order"),
                mk("2026-11-05", "question_word_order", area="expression"), mk("2026-11-05", "odd_rule")]
    t = id_types(mistakes)
    assert t["x_spelling"] == ("spelling", "")
    assert t["deadline"] == ("vocabulary", "")      # 다수결 (어휘 2 : 표현 1)
    assert t["flow"] == ("expression", "")
    assert t["question_word_order"] == ("grammar", "question")
    assert t["odd_rule"] == ("grammar", "other")


def test_recurrence_by_type_counts_ids_on_two_or_more_days():
    mistakes = [mk("2026-11-05", "question_word_order"), mk("2026-11-06", "question_word_order"),
                mk("2026-11-05", "article_missing"), mk("2026-11-05", "article_missing"),  # 같은 날 2번 = 1일
                mk("2026-11-05", "x_spelling", area="spelling")]
    rows = {(r["level"], r["group"]): r for r in recurrence_by_type(mistakes)}
    assert (rows[("area", "grammar")]["n_ids"], rows[("area", "grammar")]["n_multi_day"]) == (2, 1)
    assert rows[("area", "grammar")]["n_records"] == 4
    assert rows[("grammar", "question")]["multi_share"] == 1.0
    assert rows[("grammar", "article_noun")]["multi_share"] == 0.0
    assert rows[("area", "spelling")]["n_ids"] == 1


def test_survival_rows_use_workday_index_and_censor_and_drop_last_day():
    days = ["2026-11-05", "2026-11-06", "2026-11-09", "2026-11-10"]
    mistakes = [mk("2026-11-05", "a"), mk("2026-11-09", "a"), mk("2026-11-10", "a"),   # 2근무일 뒤 재발
                mk("2026-11-06", "b"),                                                 # 재발 없음: 2근무일 관측 후 중단
                mk("2026-11-10", "c")]                                                 # 마지막 날 처음: 관측 0 → 제외
    rows = {r["mistake_id"]: r for r in survival_rows(mistakes, days)}
    assert (rows["a"]["time"], rows["a"]["event"]) == (2, 1)
    assert (rows["b"]["time"], rows["b"]["event"]) == (2, 0)
    assert "c" not in rows


def test_kaplan_meier_steps_and_censoring():
    rows = [{"time": 1, "event": 1}, {"time": 2, "event": 0}, {"time": 3, "event": 1}, {"time": 3, "event": 0}]
    km = kaplan_meier(rows)
    assert [(p["time"], p["at_risk"], p["events"], p["survival"]) for p in km] == [
        (0, 4, 0, 1.0), (1, 4, 1, 0.75), (2, 3, 0, 0.75), (3, 2, 1, 0.375)]
