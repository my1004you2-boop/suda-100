"""6일차: 모드 배분 점검 + 후반부 비교 기준 고정.

실행 (회화앱 폴더에서, prep 다음에):
    python -m analysis.balance

- 모드별 대화 수·메시지 수를 전반부(11/5~11/11) / 후반부(11/12~)로 나눠 보여 준다.
- 대화 스타일별로 어느 날짜에 나왔는지 보여 준다 (같은 스타일끼리만 깨끗하게 비교할 수 있다).
- 전반부 실수 ID 목록을 analysis/first_half_ids.csv로 **한 번만** 고정한다 (A 분석의 분모).
  이미 있으면 덮어쓰지 않는다. 다시 만들려면 --force.
  ID와 날짜·횟수만 들어 있고 대화 원문이 없어 git에 올린다.
"""

import argparse
import csv
from pathlib import Path

from analysis.interim import AI_SINCE, MIN_MINUTES, MODE_KO, STYLE_KO
from analysis.metrics import OUT, ROOT, _read, _t

FIRST_HALF_END = "2026-11-11"   # 5일차 (중간 점검)까지가 전반부
TARGET_PER_MODE = 4             # 10일간 모드마다 최소 대화 수
FROZEN = ROOT / "analysis" / "first_half_ids.csv"
FROZEN_COLS = ["mistake_id", "n_days", "n_records", "first_date", "last_date"]


def mode_balance(sessions: list[dict], messages: list[dict], since: str = AI_SINCE,
                 split: str = FIRST_HALF_END) -> list[dict]:
    """모드별 3분 이상 대화 수와 메시지 수, 전반부·후반부."""
    ok = [s for s in sessions if s["date"] >= since and float(s["minutes"]) >= MIN_MINUTES]
    mode_of = {s["session_id"]: s["mode"] for s in sessions if s["date"] >= since}
    out = []
    for mode in MODE_KO:
        first = [s for s in ok if s["mode"] == mode and s["date"] <= split]
        second = [s for s in ok if s["mode"] == mode and s["date"] > split]
        msgs = [m for m in messages if mode_of.get(m["session_id"]) == mode]
        out.append({"mode": mode, "sessions_first": len(first), "sessions_second": len(second),
                    "sessions_total": len(first) + len(second),
                    "msgs_first": sum(m["date"] <= split for m in msgs),
                    "msgs_second": sum(m["date"] > split for m in msgs),
                    "short_of_target": max(0, TARGET_PER_MODE - len(first) - len(second))})
    return out


def style_dates(sessions: list[dict], since: str = AI_SINCE) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for s in sorted(sessions, key=lambda s: s["date"]):
        if s["date"] >= since and s["date"] not in out.setdefault(s["style"], []):
            out[s["style"]].append(s["date"])
    return out


def first_half_ids(mistakes: list[dict], end: str = FIRST_HALF_END) -> list[dict]:
    """전반부(end까지) 유효한 실수의 ID 목록. 후반부 재등장 비율의 분모."""
    agg: dict[str, dict] = {}
    for m in mistakes:
        if m["date"] > end or not _t(m["valid"]) or not m["mistake_id"]:
            continue
        a = agg.setdefault(m["mistake_id"], {"mistake_id": m["mistake_id"], "dates": set(), "n_records": 0})
        a["dates"].add(m["date"])
        a["n_records"] += 1
    rows = []
    for a in agg.values():
        d = sorted(a["dates"])
        rows.append({"mistake_id": a["mistake_id"], "n_days": len(d), "n_records": a["n_records"],
                     "first_date": d[0], "last_date": d[-1]})
    return sorted(rows, key=lambda r: (-r["n_days"], -r["n_records"], r["mistake_id"]))


def freeze(rows: list[dict], path: Path = FROZEN, force: bool = False) -> bool:
    """처음 한 번만 쓴다. 이미 있으면 False (후반부에 매핑을 고쳐도 분모가 흔들리지 않게)."""
    if path.exists() and not force:
        return False
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FROZEN_COLS)
        w.writeheader()
        w.writerows(rows)
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="전반부 ID 목록을 다시 만든다")
    args = ap.parse_args()
    sessions, messages, mistakes = (_read(OUT / f) for f in ("sessions.csv", "messages.csv", "mistakes.csv"))

    print(f"[모드 배분] 3분 이상 대화, {AI_SINCE[5:]}~  (목표: 모드마다 {TARGET_PER_MODE}회 이상)")
    print("  모드        전반부  후반부  합계   메시지(전반/후반)  부족")
    for r in mode_balance(sessions, messages):
        print(f"  {MODE_KO[r['mode']]:<8} {r['sessions_first']:>6} {r['sessions_second']:>7} {r['sessions_total']:>5}"
              f"   {r['msgs_first']:>5} / {r['msgs_second']:<5}      {r['short_of_target'] or '-'}")

    print("\n[대화 스타일별 날짜]  2번 이상 나온 스타일만 같은 조건 비교 가능")
    for style, dates in style_dates(sessions).items():
        mark = "  ← 비교 가능" if len(dates) > 1 else ""
        print(f"  {STYLE_KO.get(style, style):<8} {', '.join(d[5:] for d in dates)}{mark}")

    rows = first_half_ids(mistakes)
    wrote = freeze(rows, force=args.force)
    multi = sum(r["n_days"] > 1 for r in rows)
    print(f"\n[전반부 실수 ID] ~{FIRST_HALF_END[5:]}: {len(rows)}개 (2일 이상 {multi}개)")
    print(f"  {'새로 고정' if wrote else '이미 고정됨 (그대로 둠)'}: {FROZEN}")


if __name__ == "__main__":
    main()
