"""중간 점검 (5일차): 모드·대화 스타일별 지표, 누적 재발률, 하루 재발률의 불확실성, 추이 그래프.

실행 (회화앱 폴더에서, prep 다음에):
    python -m analysis.prep
    python -m analysis.interim

만드는 파일
- analysis/out/by_mode.csv, by_style.csv, recurrence.csv  (지표 표)
- analysis/figures/trend.png                              (추이 그래프, 숫자만 있어 git에 올림)
"""

import csv
import math
from pathlib import Path

from analysis.metrics import COLS, OUT, ROOT, TTR_WORDS, _WORD, _read, _t, summarize

FIG = ROOT / "analysis" / "figures"
AI_SINCE = "2026-11-05"  # AI 판정 지표의 기준선 날짜 (baseline.md)
MIN_MINUTES = 3.0  # 3분 미만 대화는 대화 단위 집계(대화 수, 모드 배분)에서 뺀다
STYLE_KO = {"goal_roleplay": "목표 역할극", "ai_story": "AI 이야기", "ai_disagree": "AI 반대",
            "user_first": "내가 이끌기", "ai_secret": "AI 비밀", "role_swap": "역할 바꾸기"}
MODE_KO = {"daily": "일상", "business": "비즈니스", "verb": "동사", "pattern": "표현"}
GROUP_COLS = ["group"] + [c for c in COLS if c != "date"] + ["dates"]


def by_group(sessions, messages, mistakes, col: str, since: str = "") -> list[dict]:
    """대화의 mode 또는 style로 묶어 지표를 계산한다. 3분 미만 대화는 대화 수에서 뺀다.
    since: 이 날짜부터만 (AI 판정 지표는 채점 조건이 같은 11/5부터 비교)."""
    group_of = {s["session_id"]: s[col] for s in sessions if s["date"] >= since}
    out = []
    for g in sorted(set(group_of.values())):
        ids = {k for k, v in group_of.items() if v == g}
        ss = [s for s in sessions if s["session_id"] in ids and float(s["minutes"]) >= MIN_MINUTES]
        ms = [m for m in messages if m["session_id"] in ids]
        mk = [m for m in mistakes if m["session_id"] in ids]
        dates = sorted({s["date"] for s in sessions if s["session_id"] in ids})
        out.append({"group": g, **summarize(ss, ms, mk), "dates": " ".join(d[5:] for d in dates)})
    return out


def cumulative_recurrence(mistakes: list[dict]) -> list[dict]:
    """날짜마다 '지금까지 나온 실수 ID 중 2일 이상 나온 비율'. 하루 표본이 작아 출렁이는 재발률을 보완한다."""
    valid = [m for m in mistakes if _t(m["valid"]) and m["mistake_id"]]
    out = []
    for d in sorted({m["date"] for m in valid}):
        days: dict[str, set] = {}
        for m in valid:
            if m["date"] <= d:
                days.setdefault(m["mistake_id"], set()).add(m["date"])
        multi = sum(len(v) > 1 for v in days.values())
        out.append({"date": d, "n_ids": len(days), "n_multi_day": multi, "cum_recurrence": round(multi / len(days), 3)})
    return out


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """비율 k/n의 95% 신뢰구간 (Wilson). 표본이 작을 때도 0~1을 벗어나지 않는다."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3))


def words_per_day(messages: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for m in messages:
        out[m["date"]] = out.get(m["date"], 0) + len(_WORD.findall(m["text"]))
    return out


def _write(path: Path, rows: list[dict], cols: list[str]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def plot_trend(daily: list[dict], styles: dict[str, str], path: Path, ci: dict | None = None) -> None:
    """핵심 지표 6개를 작은 그래프 여러 개로 (축 하나에 지표 하나). 기준선은 점선."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False})
    ink, muted, grid, surface, blue = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb", "#2a78d6"
    panels = [  # (컬럼, 제목, 기준 날짜, 비율인지, 11/4가 AI 판정 지표인지)
        ("avg_words", "메시지당 평균 단어 수", "2026-11-04", False, False),
        ("ttr150", "어휘 다양성 (앞 150단어 TTR)", "2026-11-04", False, False),
        ("corrected_rate", "교정받은 비율", "2026-11-05", True, True),
        ("mistakes_per_msg", "메시지당 실수 수", "2026-11-05", False, True),
        ("lead_rate", "주도율 (먼저 이야기 또는 질문)", "2026-11-05", True, True),
        ("repeat_rate", "재발 비율 (그날 실수 중 이전에 나온 것)", None, True, True),
    ]
    dates = [r["date"] for r in daily]
    xlabels = [f"{int(d[5:7])}/{int(d[8:])}\n{STYLE_KO.get(styles.get(d, ''), '')}" for d in dates]
    fig, axes = plt.subplots(2, 3, figsize=(15, 8.2), facecolor=surface)
    for ax, (col, title, base, pct, ai) in zip(axes.flat, panels):
        ax.set_facecolor(surface)
        pts = [(i, float(r[col])) for i, r in enumerate(daily) if r[col] not in ("", None)]
        if col == "repeat_rate":
            pts = [(i, v) for i, v in pts if dates[i] != "2026-11-04"]  # 첫날은 이전 기록이 없어 항상 0
        solid = [(i, v) for i, v in pts if not (ai and dates[i] == "2026-11-04")]
        ax.plot([i for i, _ in solid], [v for _, v in solid], color=blue, linewidth=2, marker="o", markersize=8,
                markeredgecolor=surface, markeredgewidth=2, zorder=3)
        for i, v in pts:
            if ai and dates[i] == "2026-11-04":  # 채점 모델이 달랐을 수 있는 날: 속 빈 회색 점
                ax.plot(i, v, marker="o", markersize=8, markerfacecolor=surface, markeredgecolor=muted,
                        markeredgewidth=1.5, zorder=3)
        if base and base in dates:  # 기준선: 점선, 값은 제목 옆에 (선 위 라벨은 점과 겹친다)
            bv = float(daily[dates.index(base)][col])
            ax.axhline(bv, color=muted, linewidth=1, linestyle=(0, (4, 3)), zorder=1)
            title += f"   기준 {bv:.0%} ({int(base[5:7])}/{int(base[8:])})" if pct else                 f"   기준 {bv:g} ({int(base[5:7])}/{int(base[8:])})"
        if col == "repeat_rate" and ci:  # 하루 실수 10~23건이라 구간이 넓다
            band = [(i, *ci[dates[i]]) for i, _ in pts if dates[i] in ci]
            ax.fill_between([b[0] for b in band], [b[1] for b in band], [b[2] for b in band], color=blue,
                            alpha=0.12, linewidth=0, zorder=1)
            title += "   띠 = 95% 구간"
        last_i, last_v = pts[-1]
        txt = f"{last_v:.0%}" if pct else (f"{last_v:.2f}" if col == "ttr150" else f"{last_v:g}")
        ax.annotate(txt, (last_i, last_v), textcoords="offset points", xytext=(9, 0), ha="left", va="center",
                    fontsize=10, color=ink, fontweight="bold")  # 점 오른쪽: 기준 점선과 겹치지 않게
        ax.set_title(title, loc="left", fontsize=11.5, color=ink, pad=10)
        ax.set_xticks(range(len(dates)), xlabels, fontsize=8.5, color=muted)
        ax.set_xlim(-0.5, len(dates) - 0.2)
        if pct:
            ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
        ax.tick_params(axis="y", labelsize=9, colors=muted, length=0)
        ax.tick_params(axis="x", length=0)
        ax.grid(axis="y", color=grid, linewidth=0.8)
        ax.set_axisbelow(True)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(grid)
        lo, hi = ax.get_ylim()
        if col == "ttr150":
            ax.set_ylim(0.4, 0.75)  # 좁은 축은 작은 차이를 크게 보이게 한다
        else:
            ax.set_ylim(min(0, lo), hi + (hi - lo) * 0.12)
    fig.suptitle("수다백단 전반부 지표 추이 (11/4 ~ 11/11)", x=0.01, ha="left", fontsize=15, color=ink,
                 fontweight="bold")
    fig.text(0.01, 0.925, "점선 = 기준선 · 속 빈 회색 점 = 11/4 (채점 모델이 달랐을 가능성, 비교에서 제외) · "
             "x축 아래 = 그날 대화 스타일", fontsize=9.5, color=muted)
    fig.tight_layout(rect=(0, 0, 1, 0.91), h_pad=2.5)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, facecolor=surface)
    plt.close(fig)


def main() -> None:
    sessions, messages, mistakes = (_read(OUT / f) for f in ("sessions.csv", "messages.csv", "mistakes.csv"))
    daily = _read(OUT / "daily_metrics.csv")
    for col, name in (("mode", "by_mode"), ("style", "by_style")):
        rows = by_group(sessions, messages, mistakes, col, since=AI_SINCE)
        _write(OUT / f"{name}.csv", rows, GROUP_COLS)
        print(f"\n[{name}]")
        for r in rows:
            print(f"  {r['group']:<14} 대화 {r['n_sessions']}  메시지 {r['n_msgs']:>3}  단어 {r['avg_words']:>5}  "
                  f"교정 {r['corrected_rate']:>5}  실수 {r['mistakes_per_msg']:>5}  주도 {r['lead_rate']:>5}  "
                  f"질문 {r['question_rate']:>5}  ({r['dates']})")
    print("\n[모드 x 날짜] 교정 비율 (메시지 수)")
    for mode in MODE_KO:
        cells = []
        for d in sorted({x["date"] for x in sessions if x["date"] >= AI_SINCE}):
            ids = {x["session_id"] for x in sessions if x["date"] == d and x["mode"] == mode}
            ms = [m for m in messages if m["session_id"] in ids]
            if ms:
                cells.append(f"{d[5:]} {sum(_t(m['corrected']) for m in ms) / len(ms):.0%}({len(ms)})")
        print(f"  {mode:<9} " + "  ".join(cells))
    rec = cumulative_recurrence(mistakes)
    by_date = {r["date"]: r for r in daily}
    for r in rec:
        d = by_date.get(r["date"], {})
        n = int(d.get("n_mistakes") or 0)  # 유효 실수 중 ID 있는 것 = 매핑이 끝났으면 n_mistakes와 같다
        r["daily_repeat"], r["daily_n"] = d.get("repeat_rate", ""), n
        r["ci_low"], r["ci_high"] = wilson(int(d.get("n_repeat") or 0), n)
    _write(OUT / "recurrence.csv", rec, ["date", "n_ids", "n_multi_day", "cum_recurrence", "daily_repeat", "daily_n",
                                         "ci_low", "ci_high"])
    print("\n[recurrence]  날짜  누적재발률  하루재발률 (95% 구간)")
    for r in rec:
        print(f"  {r['date']}  {r['n_multi_day']}/{r['n_ids']} = {r['cum_recurrence']}   "
              f"{r['daily_repeat']} ({r['ci_low']}~{r['ci_high']}, n={r['daily_n']})")
    print(f"\n[하루 단어 수]  TTR은 앞 {TTR_WORDS}단어로 계산")
    for d, n in sorted(words_per_day(messages).items()):
        print(f"  {d}  {n}단어{'  ← 부족' if n < TTR_WORDS else ''}")
    styles = {}
    for s in sessions:
        styles.setdefault(s["date"], s["style"])
    plot_trend(daily, styles, FIG / "trend.png", ci={r["date"]: (r["ci_low"], r["ci_high"]) for r in rec})
    print(f"\n그래프: {FIG / 'trend.png'}")


if __name__ == "__main__":
    main()
