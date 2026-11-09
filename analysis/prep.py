"""수다백단 대화 기록(data/sessions/*.json)을 분석용 CSV로 바꾼다.

실행 (회화앱 폴더에서):
    python -m analysis.prep

만드는 파일 (analysis/out/, git 제외):
    sessions.csv   대화 1회 = 1행
    messages.csv   내 메시지 1개 = 1행
    mistakes.csv   AI가 기록한 실수 1건 = 1행 (+ 사람이 붙인 mistake_id, 품질 표시, 재발 여부)
    practice.csv   숨은 연습 대상 key × 날짜
    warnings.txt   데이터 품질 경고

사람이 고치는 파일 (git 제외):
    analysis/mistake_map.csv   (원문, 교정문) → mistake_id. 처음 보는 실수는 ID 빈칸으로 끝에 덧붙는다.

여러 번 돌려도 결과가 같다 (항상 처음부터 다시 만든다. 매핑표는 덧붙이기만 한다).
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
MISTAKE_COLS = ["session_id", "date", "day_n", "work_day", "mode", "style", "msg_idx", "user_text", "key", "area",
                "original", "native", "voice_sensitive", "prompt_version", "not_in_text", "dup_in_msg", "valid",
                "mistake_id", "occurrence_n", "repeat"]
PRACTICE_COLS = ["date", "key", "n_sessions", "used_correctly", "mistaken_again"]
MAP_COLS = ["mistake_id", "original", "native", "first_date"]
DEFAULT_MAP = ROOT / "analysis" / "mistake_map.csv"
_PUNCT = re.compile(r"[^\w\s']")


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


def norm(text: str) -> str:
    """비교용: 소문자, 문장부호 제거, 띄어쓰기 하나로."""
    return " ".join(_PUNCT.sub(" ", text.lower()).split())


def in_text(original: str, text: str) -> bool:
    """AI가 적은 '틀린 말'이 내 메시지에 실제로 있는지. 단어 80% 이상이 메시지에 있으면 있다고 본다."""
    o, t = norm(original), norm(text)
    if not o or o in t:
        return True
    words = o.split()
    have = set(t.split())
    return sum(w in have for w in words) / len(words) >= 0.8


def _map_key(original: str, native: str) -> tuple[str, str]:
    return norm(original), norm(native)


def read_map(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [{c: r.get(c, "") or "" for c in MAP_COLS} for r in csv.DictReader(f)]


def write_map(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(path, MAP_COLS, rows)


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


def build_mistakes(sessions: list[dict], map_rows: list[dict]) -> tuple[list[dict], list[dict], list[str]]:
    """실수 1건 = 1행. 매핑표에 없는 실수는 매핑표 끝에 덧붙인다 (ID 빈칸)."""
    index = {_map_key(r["original"], r["native"]): r for r in map_rows}
    rows = []
    for s in sessions:
        user_msgs = [m for m in s.get("messages", []) if m["role"] == "user"]
        for i, t in enumerate(s.get("turns", [])):
            text = user_msgs[i]["text"] if i < len(user_msgs) else ""
            seen = set()
            for m in t.get("mistakes") or []:
                k = _map_key(m["original"], m["native"])
                dup = norm(m["original"]) in seen
                seen.add(norm(m["original"]))
                if k not in index:
                    index[k] = {"mistake_id": "", "original": m["original"], "native": m["native"],
                                "first_date": s["date"]}
                    map_rows.append(index[k])
                not_in = not in_text(m["original"], text)
                rows.append({
                    "session_id": s["id"], "date": s["date"], "day_n": day_n(s["date"]),
                    "work_day": _blank(work_day(s["date"])), "mode": s.get("mode", ""), "style": s.get("style", ""),
                    "msg_idx": i + 1, "user_text": text, "key": m.get("key", ""), "area": m.get("area", ""),
                    "original": m["original"], "native": m["native"],
                    "voice_sensitive": bool(m.get("voice_sensitive")),
                    "prompt_version": s.get("prompt_version", ""), "not_in_text": not_in, "dup_in_msg": dup,
                    "valid": not (not_in or dup), "mistake_id": index[k]["mistake_id"],
                })

    # 재발: 유효한 기록만, mistake_id 기준으로 센다
    count: dict[str, int] = {}
    dates: dict[str, set] = {}
    for r in rows:
        mid = r["mistake_id"]
        if not (r["valid"] and mid):
            r["occurrence_n"] = r["repeat"] = ""
            continue
        count[mid] = count.get(mid, 0) + 1
        earlier = dates.setdefault(mid, set())
        r["occurrence_n"] = count[mid]
        r["repeat"] = any(d < r["date"] for d in earlier)
        earlier.add(r["date"])

    warnings = []
    for r in rows:
        if r["not_in_text"]:
            warnings.append(f"{r['session_id']} #{r['msg_idx']}: 말하지 않은 실수 기록 \"{r['original']}\" "
                            f"(내 메시지: \"{r['user_text']}\")")
        if r["dup_in_msg"]:
            warnings.append(f"{r['session_id']} #{r['msg_idx']}: 한 메시지 안 중복 실수 \"{r['original']}\"")
    unmapped = sum(1 for r in map_rows if not r["mistake_id"])
    if unmapped:
        warnings.append(f"ID 없는 실수 {unmapped}건: analysis/mistake_map.csv의 mistake_id 빈칸을 채워 주세요")
    return rows, map_rows, warnings


def build_practice(data_dir: Path, sessions: list[dict]) -> list[dict]:
    """숨은 연습 대상(plans/{date}.json targets)을 그날 맞게 썼는지 / 또 틀렸는지. AI key 기준."""
    rows = []
    for p in sorted((data_dir / "plans").glob("*.json")) if (data_dir / "plans").exists() else []:
        plan = json.loads(p.read_text(encoding="utf-8"))
        d = plan.get("date", p.stem)
        day = [s for s in sessions if s["date"] == d]
        used = {k for s in day for t in s.get("turns", []) for k in t.get("targets_used_correctly") or []}
        wrong = {m.get("key") for s in day for t in s.get("turns", []) for m in t.get("mistakes") or []}
        for k in plan.get("targets", []):
            rows.append({"date": d, "key": k, "n_sessions": len(day), "used_correctly": k in used,
                         "mistaken_again": k in wrong})
    return rows


def _write_csv(path: Path, cols: list[str], rows: list[dict]) -> None:
    # utf-8-sig: 엑셀에서 열어도 한글이 깨지지 않게
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def run(data_dir: Path, out_dir: Path, map_path: Path = DEFAULT_MAP) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    sessions = load_sessions(data_dir)
    session_rows, message_rows, warnings = build_rows(sessions)
    mistake_rows, map_rows, mistake_warnings = build_mistakes(sessions, read_map(map_path))
    warnings += mistake_warnings
    _write_csv(out_dir / "sessions.csv", SESSION_COLS, session_rows)
    _write_csv(out_dir / "messages.csv", MESSAGE_COLS, message_rows)
    _write_csv(out_dir / "mistakes.csv", MISTAKE_COLS, mistake_rows)
    _write_csv(out_dir / "practice.csv", PRACTICE_COLS, build_practice(data_dir, sessions))
    write_map(map_path, map_rows)
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
