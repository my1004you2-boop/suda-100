"""8일차 B 분석: 내 발화는 달라졌는가.

실행 (회화앱 폴더에서, prep·metrics 다음에):
    python -m analysis.prep
    python -m analysis.metrics
    python -m analysis.speech_change

B1. 문장 길이 분포 (평균만 보면 짧은 답 몇 개에 흔들린다 → 중앙값·사분위·짧은 답/긴 문장 비율)
    어휘 다양성: 하루 앞 150단어 TTR + 50단어 조각 TTR의 평균(MSTTR, 하루 말한 양이 적어도 쓸 수 있다)
B2. 한국어 섞임·한국어로 도움 요청 (건수)
B3. 주도율·질문 비율
+ 길이 구간별 교정 비율: 교정 비율이 내려간 게 "덜 틀려서"인지 "짧게 말해서"인지 가른다
+ 같은 스타일 짝 비교 (날짜와 대화 스타일이 섞여 있어서 깨끗한 비교는 이것뿐)

만드는 파일
- analysis/out/length_profile.csv, corrected_by_length.csv, style_pairs_b.csv  (git 제외 폴더)
- analysis/figures/b_length.png, b_vocab.png, b_lead.png  (숫자만 있어 git에 올림)
"""

import csv
from pathlib import Path
from statistics import median

from analysis.balance import FIRST_HALF_END
from analysis.interim import AI_SINCE, FIG, STYLE_KO, wilson
from analysis.metrics import OUT, _WORD, _read, _t, summarize

SHORT_MAX, LONG_MIN = 3, 10      # 3단어 이하 = 짧은 답 ("Okay", "Let's go."), 10단어 이상 = 긴 문장
CHUNK = 50                       # MSTTR 조각 크기
BUCKETS = ["1-4", "5-9", "10+"]


def _quartiles(xs: list[int]) -> tuple:
    """중앙값과 아래·위 사분위 (아래 절반·위 절반의 중앙값, 홀수 개면 가운데 값을 뺀다)."""
    s = sorted(xs)
    half = len(s) // 2
    lo, hi = s[:half], s[half + (len(s) % 2):]
    return median(s), (median(lo) if lo else s[0]), (median(hi) if hi else s[-1])


def length_profile(messages: list[dict]) -> list[dict]:
    out = []
    for d in sorted({m["date"] for m in messages}):
        ws = [int(m["n_words"]) for m in messages if m["date"] == d]
        med, q1, q3 = _quartiles(ws)
        out.append({"date": d, "n_msgs": len(ws), "mean": round(sum(ws) / len(ws), 1), "median": med, "q1": q1,
                    "q3": q3, "short_share": round(sum(w <= SHORT_MAX for w in ws) / len(ws), 3),
                    "long_share": round(sum(w >= LONG_MIN for w in ws) / len(ws), 3)})
    return out


def msttr(words: list[str], size: int = CHUNK) -> tuple:
    """size단어 조각마다 TTR을 내서 평균. 남는 단어는 버린다. (평균, 조각 수)"""
    chunks = [words[i:i + size] for i in range(0, len(words) - size + 1, size)]
    if not chunks:
        return ("", 0)
    return (round(sum(len(set(c)) / size for c in chunks) / len(chunks), 3), len(chunks))


def _tokens(messages: list[dict]) -> list[str]:
    return [w.lower() for m in messages for w in _WORD.findall(m["text"])]


def bucket_of(n: int) -> str:
    return "1-4" if n <= 4 else ("5-9" if n <= 9 else "10+")


def corrected_by_length(messages: list[dict], key) -> list[dict]:
    """key(메시지)로 묶고 길이 구간마다 교정 비율. 메시지가 없는 칸은 만들지 않는다."""
    cells: dict[tuple, list] = {}
    for m in messages:
        cells.setdefault((key(m), bucket_of(int(m["n_words"]))), []).append(_t(m["corrected"]))
    out = []
    for g in sorted({k[0] for k in cells}):
        for b in BUCKETS:
            v = cells.get((g, b))
            if v:
                lo, hi = wilson(sum(v), len(v))
                out.append({"group": g, "bucket": b, "n": len(v), "corrected_rate": round(sum(v) / len(v), 3),
                            "ci_low": lo, "ci_high": hi})
    return out


def standardized_rate(rows: list[dict], group: str, ref: str) -> float:
    """group의 길이 구간별 교정 비율을 ref의 길이 구성(구간별 메시지 수)으로 가중 평균.
    "group이 ref만큼 길게 말했다면 교정 비율이 얼마였을까" (직접 표준화)."""
    rate = {r["bucket"]: r["corrected_rate"] for r in rows if r["group"] == group}
    weight = {r["bucket"]: r["n"] for r in rows if r["group"] == ref and r["bucket"] in rate}
    return round(sum(rate[b] * n for b, n in weight.items()) / sum(weight.values()), 3)


def style_pairs(sessions: list[dict], messages: list[dict], mistakes: list[dict], since: str = AI_SINCE) -> list[dict]:
    """2개 이상 날짜에 나온 대화 스타일만, 날짜마다 B 지표."""
    style_of = {s["session_id"]: s["style"] for s in sessions if s["date"] >= since}
    dates: dict[str, set] = {}
    for s in sessions:
        if s["session_id"] in style_of:
            dates.setdefault(s["style"], set()).add(s["date"])
    out = []
    for style in sorted(dates, key=lambda k: min(dates[k])):
        if len(dates[style]) < 2:
            continue
        for d in sorted(dates[style]):
            ids = {sid for sid, st in style_of.items() if st == style}
            ms = [m for m in messages if m["session_id"] in ids and m["date"] == d]
            ss = [s for s in sessions if s["session_id"] in ids and s["date"] == d]
            mk = [m for m in mistakes if m["session_id"] in ids and m["date"] == d]
            sm = summarize(ss, ms, mk)
            ws = [int(m["n_words"]) for m in ms]
            out.append({"style": style, "date": d, "n_msgs": len(ms), "avg_words": sm["avg_words"],
                        "median_words": sm["median_words"],
                        "long_share": round(sum(w >= LONG_MIN for w in ws) / len(ws), 3) if ws else "",
                        "msttr50": msttr(_tokens(ms))[0], "corrected_rate": sm["corrected_rate"],
                        "lead_rate": sm["lead_rate"], "question_rate": sm["question_rate"],
                        "korean_n": sum(_t(m["has_korean"]) for m in ms),
                        "help_n": sum(_t(m["asked_help_ko"]) for m in ms)})
    return out


def _write(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


# ---------- 그래프 ----------
INK, MUTED, GRID, SURFACE, BLUE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb", "#2a78d6"


def _setup():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False})
    return matplotlib, plt


def _axes_style(ax, xlabels, pct=False):
    import matplotlib.ticker as mt

    ax.set_facecolor(SURFACE)
    ax.set_xticks(range(len(xlabels)), xlabels, fontsize=8.5, color=MUTED)
    ax.set_xlim(-0.5, len(xlabels) - 0.2)
    ax.tick_params(axis="y", labelsize=9, colors=MUTED, length=0)
    ax.tick_params(axis="x", length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    if pct:
        ax.yaxis.set_major_formatter(mt.PercentFormatter(1.0, decimals=0))


def _line(ax, xs, ys, fmt):
    ax.plot(xs, ys, color=BLUE, linewidth=2, marker="o", markersize=7, markeredgecolor=SURFACE,
            markeredgewidth=2, zorder=3)
    ax.annotate(fmt(ys[-1]), (xs[-1], ys[-1]), textcoords="offset points", xytext=(9, 0), va="center",
                fontsize=10, color=INK, fontweight="bold")


def _split(ax, dates):
    """전반부/후반부 경계 세로 점선."""
    k = sum(d <= FIRST_HALF_END for d in dates)
    if 0 < k < len(dates):
        ax.axvline(k - 0.5, color=MUTED, linewidth=1, linestyle=(0, (4, 3)), zorder=1)


def _finish(fig, plt, path, title, note):
    fig.suptitle(title, x=0.01, ha="left", fontsize=14, color=INK, fontweight="bold")
    fig.text(0.01, 0.015, note, fontsize=9, color=MUTED)
    fig.tight_layout(rect=(0, 0.04, 1, 0.93), h_pad=2.2)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def _xlabels(dates, styles):
    """날짜 + 대화 스타일 (스타일 이름은 두 줄로 접어 옆 라벨과 겹치지 않게)."""
    return [f"{int(d[5:7])}/{int(d[8:])}\n" + STYLE_KO.get(styles.get(d, ""), "").replace(" ", "\n") for d in dates]


def plot_length(profile: list[dict], styles: dict, path: Path) -> None:
    _, plt = _setup()
    dates = [r["date"] for r in profile]
    xs, xl = list(range(len(dates))), _xlabels(dates, styles)
    fig, axes = plt.subplots(1, 3, figsize=(17, 5), facecolor=SURFACE)
    ax = axes[0]
    _axes_style(ax, xl)
    ax.fill_between(xs, [r["q1"] for r in profile], [r["q3"] for r in profile], color=BLUE, alpha=0.13,
                    linewidth=0, zorder=1)
    _line(ax, xs, [r["median"] for r in profile], lambda v: f"{v:g}")
    ax.set_ylim(0, max(r["q3"] for r in profile) * 1.2)
    ax.set_title("메시지 단어 수 중앙값   띠 = 가운데 50%", loc="left", fontsize=11, color=INK, pad=10)
    for ax, col, title in ((axes[1], "short_share", f"짧은 답 비율 ({SHORT_MAX}단어 이하)"),
                           (axes[2], "long_share", f"긴 문장 비율 ({LONG_MIN}단어 이상)")):
        _axes_style(ax, xl, pct=True)
        _line(ax, xs, [r[col] for r in profile], lambda v: f"{v:.0%}")
        ax.set_ylim(0, max(0.6, max(r[col] for r in profile) * 1.2))
        ax.set_title(title, loc="left", fontsize=11, color=INK, pad=10)
    for ax in axes:
        _split(ax, dates)
    _finish(fig, plt, path, "B1. 내 메시지 길이 (11/4~)",
            "세로 점선 = 전반부 | 후반부 경계 · x축 아래 = 그날 대화 스타일")


def plot_vocab(daily: list[dict], ms_by_day: dict, styles: dict, path: Path) -> None:
    _, plt = _setup()
    dates = [r["date"] for r in daily]
    xs, xl = list(range(len(dates))), _xlabels(dates, styles)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), facecolor=SURFACE)
    for ax, vals, title in ((axes[0], [float(r["ttr150"]) if r["ttr150"] else None for r in daily],
                             "앞 150단어 TTR (하루 1개 값)"),
                            (axes[1], [ms_by_day[d][0] for d in dates], f"{CHUNK}단어 조각 TTR 평균 (MSTTR)")):
        _axes_style(ax, xl)
        pts = [(x, v) for x, v in zip(xs, vals) if v not in (None, "")]
        _line(ax, [p[0] for p in pts], [p[1] for p in pts], lambda v: f"{v:.2f}")
        ax.set_ylim(0.4, 0.9)   # 같은 축 범위로 두 그래프를 맞춘다
        ax.set_title(title, loc="left", fontsize=11, color=INK, pad=10)
        _split(ax, dates)
    _finish(fig, plt, path, "B1. 어휘 다양성 (서로 다른 단어 수 / 전체 단어 수)",
            f"MSTTR = 그날 말한 단어를 {CHUNK}단어씩 잘라 각각 TTR을 낸 평균 · 세로 점선 = 전반부 | 후반부 경계")


def plot_lead(daily: list[dict], styles: dict, path: Path) -> None:
    _, plt = _setup()
    rows = [r for r in daily if r["date"] >= AI_SINCE]   # AI 판정 지표: 11/5부터
    dates = [r["date"] for r in rows]
    xs, xl = list(range(len(dates))), _xlabels(dates, styles)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), facecolor=SURFACE)
    for ax, col, title in ((axes[0], "lead_rate", "주도율 (먼저 이야기를 꺼내거나 질문한 메시지)"),
                           (axes[1], "question_rate", "질문 비율")):
        _axes_style(ax, xl, pct=True)
        _line(ax, xs, [float(r[col]) for r in rows], lambda v: f"{v:.0%}")
        ax.set_ylim(0, 0.75)
        ax.set_title(title, loc="left", fontsize=11, color=INK, pad=10)
        _split(ax, dates)
    _finish(fig, plt, path, "B3. 내가 대화를 이끄는 비율 (11/5~, AI 판정)",
            "세로 점선 = 전반부 | 후반부 경계 · 대화 스타일에 따라 크게 달라진다 (x축 아래)")


def main() -> None:
    sessions, messages, mistakes = (_read(OUT / f) for f in ("sessions.csv", "messages.csv", "mistakes.csv"))
    daily = _read(OUT / "daily_metrics.csv")
    styles = {}
    for s in sessions:
        styles.setdefault(s["date"], s["style"])

    profile = length_profile(messages)
    ms_by_day = {d: msttr(_tokens([m for m in messages if m["date"] == d])) for d in {m["date"] for m in messages}}
    for r in profile:
        r["msttr50"], r["msttr_chunks"] = ms_by_day[r["date"]]
    _write(OUT / "length_profile.csv", profile)
    print("[B1] 날짜      메시지  평균  중앙값(사분위)  짧은답  긴문장  MSTTR50(조각)")
    for r in profile:
        print(f"  {r['date']}  {r['n_msgs']:>3}  {r['mean']:>5}  {r['median']:>4g} ({r['q1']:g}~{r['q3']:g})"
              f"  {r['short_share']:>5.0%}  {r['long_share']:>5.0%}  {r['msttr50']} ({r['msttr_chunks']})")

    print("\n[B2] 한국어 섞인 메시지 / 한국어로 도움 요청")
    for d in sorted({m["date"] for m in messages}):
        ms = [m for m in messages if m["date"] == d]
        print(f"  {d}  {sum(_t(m['has_korean']) for m in ms)} / {sum(_t(m['asked_help_ko']) for m in ms)}"
              f"  (메시지 {len(ms)})")

    print("\n[B3] 스타일별 주도율·질문 비율 (11/5~)")
    for st in sorted({s["style"] for s in sessions if s["date"] >= AI_SINCE}):
        ids = {s["session_id"] for s in sessions if s["style"] == st and s["date"] >= AI_SINCE}
        ms = [m for m in messages if m["session_id"] in ids]
        lead = sum(_t(m["user_led"]) or _t(m["user_asked_question"]) for m in ms)
        q = sum(_t(m["user_asked_question"]) for m in ms)
        print(f"  {STYLE_KO.get(st, st):<8} 메시지 {len(ms):>3}  주도 {lead / len(ms):.0%}  질문 {q / len(ms):.0%}")

    ai = [m for m in messages if m["date"] >= AI_SINCE]
    by_len = corrected_by_length(ai, key=lambda m: "전반부" if m["date"] <= FIRST_HALF_END else "후반부")
    _write(OUT / "corrected_by_length.csv", by_len)
    print("\n[길이 구간별 교정 비율] 11/5~  (95% 구간)")
    for r in by_len:
        print(f"  {r['group']}  {r['bucket']:>4}단어  {r['corrected_rate']:.0%}  "
              f"({r['ci_low']:.0%}~{r['ci_high']:.0%}, n={r['n']})")

    raw = {g: sum(r["corrected_rate"] * r["n"] for r in by_len if r["group"] == g) /
           sum(r["n"] for r in by_len if r["group"] == g) for g in ("전반부", "후반부")}
    print(f"  전체: 전반부 {raw['전반부']:.0%} → 후반부 {raw['후반부']:.0%}  |  "
          f"후반부를 전반부 길이 구성으로 맞추면 {standardized_rate(by_len, '후반부', '전반부'):.0%}")

    pairs = style_pairs(sessions, messages, mistakes)
    _write(OUT / "style_pairs_b.csv", pairs)
    print("\n[같은 스타일 짝]  메시지  평균/중앙값  긴문장  MSTTR  교정  주도  질문")
    for r in pairs:
        print(f"  {STYLE_KO.get(r['style'], r['style']):<8} {r['date']}  {r['n_msgs']:>3}  "
              f"{r['avg_words']}/{r['median_words']:g}  {r['long_share']:.0%}  {r['msttr50']}  "
              f"{float(r['corrected_rate']):.0%}  {float(r['lead_rate']):.0%}  {float(r['question_rate']):.0%}")

    plot_length(profile, styles, FIG / "b_length.png")
    plot_vocab(daily, ms_by_day, styles, FIG / "b_vocab.png")
    plot_lead(daily, styles, FIG / "b_lead.png")
    print(f"\n그래프: {FIG / 'b_length.png'}, b_vocab.png, b_lead.png")


if __name__ == "__main__":
    main()
