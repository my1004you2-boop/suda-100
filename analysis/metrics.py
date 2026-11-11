"""prep.py가 만든 CSV로 날짜별 지표를 계산한다.

실행 (회화앱 폴더에서, prep 다음에):
    python -m analysis.prep
    python -m analysis.metrics

만드는 파일: analysis/out/daily_metrics.csv (날짜 1개 = 1행)
지표 정의: docs/데이터분석과제.md 5절, analysis/data_dictionary.md
"""

import csv
import re
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "analysis" / "out"
TTR_WORDS = 150
_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)*")

COLS = ["date", "n_sessions", "minutes", "n_msgs", "avg_words", "median_words", "ttr150", "korean_rate",
        "help_rate", "corrected_rate", "mistakes_per_msg", "lead_rate", "question_rate", "voice_rate",
        "n_mistakes", "n_repeat", "repeat_rate"]


def ttr(words: list[str], n: int = TTR_WORDS):
    """앞 n단어 중 서로 다른 단어 비율. n단어가 안 되면 빈칸 (날마다 말한 양이 달라 길이를 맞춘다)."""
    if len(words) < n:
        return ""
    return round(len(set(words[:n])) / n, 3)


def _t(v) -> bool:
    return v == "True"


def _rate(rows, col) -> float:
    return round(sum(_t(r[col]) for r in rows) / len(rows), 3) if rows else ""


def summarize(ss: list[dict], ms: list[dict], mistakes: list[dict]) -> dict:
    """대화·메시지·실수 묶음 하나의 지표. 날짜별, 모드별, 스타일별 집계에 같이 쓴다."""
    mk = [r for r in mistakes if _t(r["valid"])]
    words = [int(r["n_words"]) for r in ms]
    tokens = [w.lower() for r in ms for w in _WORD.findall(r["text"])]
    n_repeat = sum(_t(r["repeat"]) for r in mk)
    mapped = [r for r in mk if r["mistake_id"]]
    return {
        "n_sessions": len(ss), "minutes": round(sum(float(r["minutes"]) for r in ss), 1),
        "n_msgs": len(ms),
        "avg_words": round(sum(words) / len(words), 1) if words else "",
        "median_words": median(words) if words else "",
        "ttr150": ttr(tokens),
        "korean_rate": _rate(ms, "has_korean"), "help_rate": _rate(ms, "asked_help_ko"),
        "corrected_rate": _rate(ms, "corrected"),
        "mistakes_per_msg": round(len(mk) / len(ms), 2) if ms else "",
        "lead_rate": round(sum(_t(r["user_led"]) or _t(r["user_asked_question"]) for r in ms) / len(ms), 3)
        if ms else "",
        "question_rate": _rate(ms, "user_asked_question"), "voice_rate": _rate(ms, "via_voice"),
        "n_mistakes": len(mk), "n_repeat": n_repeat,
        "repeat_rate": round(n_repeat / len(mapped), 3) if mapped else "",
    }


def daily_metrics(sessions: list[dict], messages: list[dict], mistakes: list[dict]) -> list[dict]:
    out = []
    for d in sorted({r["date"] for r in sessions}):
        row = summarize([r for r in sessions if r["date"] == d], [r for r in messages if r["date"] == d],
                        [r for r in mistakes if r["date"] == d])
        out.append({"date": d, **row})
    return out


def _read(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    rows = daily_metrics(_read(OUT / "sessions.csv"), _read(OUT / "messages.csv"), _read(OUT / "mistakes.csv"))
    with open(OUT / "daily_metrics.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    show = ["date", "n_msgs", "avg_words", "ttr150", "corrected_rate", "mistakes_per_msg", "lead_rate",
            "question_rate", "n_mistakes", "n_repeat", "repeat_rate"]
    print("  ".join(f"{c:>10}" for c in show))
    for r in rows:
        print("  ".join(f"{str(r[c]):>10}" for c in show))


if __name__ == "__main__":
    main()
