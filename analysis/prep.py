"""수다백단 대화 기록(data/sessions/*.json)을 분석용 CSV로 바꾼다.

실행 (회화앱 폴더에서):
    python -m analysis.prep

만드는 파일 (analysis/out/, git 제외):
    sessions.csv   대화 1회 = 1행
    messages.csv   내 메시지 1개 = 1행
    warnings.txt   데이터 품질 경고

여러 번 돌려도 결과가 같다 (항상 처음부터 다시 만든다).
설계: docs/데이터분석과제.md 3절
"""

import argparse
import csv
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE_DATE = date(2026, 11, 4)          # day_n = 0 (기준선)
WORK_DAYS = ["2026-11-05", "2026-11-06", "2026-11-09", "2026-11-10", "2026-11-11",
             "2026-11-12", "2026-11-13", "2026-11-16", "2026-11-17", "2026-11-18"]
SHORT_SESSION_SECONDS = 180

_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)*")
_KOREAN = re.compile(r"[가-힣]")

SESSION_COLS = ["session_id", "date", "day_n", "work_day", "started", "mode", "style", "topic", "minutes",
                "finished", "model", "prompt_version", "n_user_msgs", "voice_ratio", "n_turns", "turns_match"]
MESSAGE_COLS = ["session_id", "date", "day_n", "work_day", "mode", "msg_idx", "ts", "text", "via_voice",
                "n_words", "has_korean", "asked_help_ko", "corrected", "user_asked_question", "user_led",
                "n_mistakes", "prompt_version"]


def count_words(text: str) -> int:
    """영어 단어 수. don't 같은 축약은 1단어, 숫자와 한글은 세지 않는다."""
    return len(_WORD.findall(text))


def has_korean(text: str) -> bool:
    return bool(_KOREAN.search(text))


def day_n(d: str) -> int:
    """11/4 = 0, 11/5 = 1, … 달력 기준."""
    return (date.fromisoformat(d) - BASE_DATE).days


def work_day(d: str) -> int | None:
    """근무 일차 1~10. 주말이나 기간 밖이면 None."""
    return WORK_DAYS.index(d) + 1 if d in WORK_DAYS else None


def _blank(v):
    return "" if v is None else v


def load_sessions(data_dir: Path) -> list[dict]:
    out = []
    for p in sorted((data_dir / "sessions").glob("*.json")):
        out.append(json.loads(p.read_text(encoding="utf-8")))
    return out


def build_rows(sessions: list[dict]) -> tuple[list[dict], list[dict], list[str]]:
    session_rows, message_rows, warnings = [], [], []
    for s in sessions:
        sid, d = s["id"], s["date"]
        user_msgs = [m for m in s.get("messages", []) if m["role"] == "user"]
        turns = s.get("turns", [])
        match = len(user_msgs) == len(turns)
        if not match:
            warnings.append(f"{sid}: 턴 수 불일치 (내 메시지 {len(user_msgs)}개, AI 판정 {len(turns)}개)")
        if s.get("seconds", 0) < SHORT_SESSION_SECONDS:
            warnings.append(f"{sid}: 3분 미만 대화 ({s.get('seconds', 0)}초)")
        if not s.get("finished"):
            warnings.append(f"{sid}: 끝나지 않은 대화 (finished = False)")

        common = {"session_id": sid, "date": d, "day_n": day_n(d), "work_day": _blank(work_day(d))}
        n_voice = sum(1 for m in user_msgs if m.get("via_voice"))
        session_rows.append({
            **common,
            "started": s.get("started", ""), "mode": s.get("mode", ""), "style": s.get("style", ""),
            "topic": s.get("topic", ""), "minutes": round(s.get("seconds", 0) / 60, 1),
            "finished": bool(s.get("finished")), "model": s.get("model", ""),
            "prompt_version": s.get("prompt_version", ""), "n_user_msgs": len(user_msgs),
            "voice_ratio": round(n_voice / len(user_msgs), 2) if user_msgs else "",
            "n_turns": len(turns), "turns_match": match,
        })

        for i, m in enumerate(user_msgs):
            t = turns[i] if i < len(turns) else None
            message_rows.append({
                **common, "mode": s.get("mode", ""), "msg_idx": i + 1, "ts": m.get("ts", ""),
                "text": m["text"], "via_voice": bool(m.get("via_voice")),
                "n_words": count_words(m["text"]), "has_korean": has_korean(m["text"]),
                "asked_help_ko": bool(m.get("help_ko")), "corrected": bool(m.get("correction")),
                "user_asked_question": _blank(t and bool(t.get("user_asked_question"))),
                "user_led": _blank(t and bool(t.get("user_led"))),
                "n_mistakes": _blank(t and len(t.get("mistakes") or [])),
                "prompt_version": s.get("prompt_version", ""),
            })
    return session_rows, message_rows, warnings


def _write_csv(path: Path, cols: list[str], rows: list[dict]) -> None:
    # utf-8-sig: 엑셀에서 열어도 한글이 깨지지 않게
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def run(data_dir: Path, out_dir: Path) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    session_rows, message_rows, warnings = build_rows(load_sessions(data_dir))
    _write_csv(out_dir / "sessions.csv", SESSION_COLS, session_rows)
    _write_csv(out_dir / "messages.csv", MESSAGE_COLS, message_rows)
    (out_dir / "warnings.txt").write_text("\n".join(warnings) + ("\n" if warnings else ""), encoding="utf-8")
    return warnings


def summary(out_dir: Path) -> str:
    """날짜별 요약 (근무 일지에 옮겨 적기 좋게)."""
    with open(out_dir / "messages.csv", encoding="utf-8-sig", newline="") as f:
        msgs = list(csv.DictReader(f))
    with open(out_dir / "sessions.csv", encoding="utf-8-sig", newline="") as f:
        sess = list(csv.DictReader(f))
    lines = ["날짜        대화  분   메시지  교정비율  평균단어  한국어  주도/질문"]
    for d in sorted({r["date"] for r in sess}):
        ss = [r for r in sess if r["date"] == d]
        ms = [r for r in msgs if r["date"] == d]
        n = len(ms) or 1
        corr = sum(r["corrected"] == "True" for r in ms)
        led = sum(r["user_led"] == "True" for r in ms)
        q = sum(r["user_asked_question"] == "True" for r in ms)
        lines.append(f"{d}  {len(ss):>3}  {sum(float(r['minutes']) for r in ss):>5.1f}  {len(ms):>5}  "
                     f"{corr / n:>7.0%}  {sum(int(r['n_words']) for r in ms) / n:>8.1f}  "
                     f"{sum(r['has_korean'] == 'True' for r in ms):>5}  {led:>4}/{q}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    ap.add_argument("--out", type=Path, default=ROOT / "analysis" / "out")
    args = ap.parse_args()
    warnings = run(args.data, args.out)
    print(summary(args.out))
    print(f"\n경고 {len(warnings)}건" + ("".join(f"\n  - {w}" for w in warnings)))


if __name__ == "__main__":
    main()
