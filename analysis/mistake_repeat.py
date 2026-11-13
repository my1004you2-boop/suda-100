"""7일차 A 분석: 실수는 다시 나오는가.

실행 (회화앱 폴더에서, prep 다음에):
    python -m analysis.prep
    python -m analysis.mistake_repeat

1. 재등장 비율: 전반부에 고정한 실수 ID(first_half_ids.csv) 중 후반부(11/12~)에 다시 나온 비율.
   전반부에 2일 이상 나온 ID와 1일만 나온 ID로 나눠 본다. 후반부가 다 모이기 전에는 중간값이다.
2. 유형별 재발: 실수 ID를 영역(문법·어휘·표현·철자)과 문법 세부 묶음으로 나눠, 2일 이상 나온 ID의 비율.
3. 생존 분석 (Kaplan–Meier): 처음 나온 뒤 몇 근무일 만에 다시 나오는지. 아직 다시 안 나온 ID는
   마지막 근무일에서 관측 중단(censored)으로 처리한다. 늦게 처음 나온 ID일수록 지켜본 날이 짧은 문제를 보정한다.

만드는 파일
- analysis/out/reappearance.csv, repeat_by_type.csv, survival.csv  (ID 목록이 들어가 git 제외 폴더)
- analysis/figures/a_reappearance.png, a_by_type.png, a_survival.png  (숫자만 있어 git에 올림)
"""

import csv
from collections import Counter
from pathlib import Path

from analysis.balance import FIRST_HALF_END, FROZEN
from analysis.interim import FIG, wilson
from analysis.metrics import OUT, _read, _t

SECOND_HALF_START = "2026-11-12"
AREA_NORM = {"vocabulary": "vocabulary", "어휘 선택": "vocabulary", "phrasal_flow": "expression",
             "expression": "expression", "grammar": "grammar", "spelling": "spelling"}
AREA_KO = {"grammar": "문법", "vocabulary": "어휘", "expression": "표현", "spelling": "철자"}
# 문법 실수 ID의 세부 묶음 (사람이 정함). 여기 없는 문법 ID는 "other".
GRAMMAR_GROUP = {
    "question": ["question_word_order", "question_do_support", "can_you_tell_me"],
    "tense": ["present_for_habit", "past_tense_missing", "past_irregular_verb", "present_perfect", "future_will",
              "future_plan_ing", "had_to", "if_clause_present", "conditional_if"],
    "verb_form": ["be_verb_missing", "subject_verb_agreement", "to_infinitive", "negation_do_support"],
    "article_noun": ["article_missing", "article_uncountable", "article_with_number", "plural_noun",
                     "food_uncountable", "double_determiner", "my_possessive"],
    "preposition": ["at_home", "preposition_in_episode", "preposition_missing", "preposition_on_trip",
                    "today_no_preposition", "unneeded_preposition", "listen_to_music", "song_from"],
    "connector": ["cause_connector", "and_then", "i_think_clause"],
}
GROUP_OF = {mid: g for g, ids in GRAMMAR_GROUP.items() for mid in ids}
GRAMMAR_KO = {"question": "질문 구조", "tense": "시제", "verb_form": "동사 형태·일치", "article_noun": "관사·명사 수",
              "preposition": "전치사", "connector": "연결어·절", "other": "기타 문법"}
REAPPEAR_KO = {"all": "전체", "multi_day": "전반부 2일 이상", "single_day": "전반부 1일"}


def _valid(mistakes: list[dict]) -> list[dict]:
    return [m for m in mistakes if _t(m["valid"]) and m["mistake_id"]]


def reappearance(frozen: list[dict], mistakes: list[dict], since: str = SECOND_HALF_START) -> list[dict]:
    """고정된 전반부 ID 중 since 이후 유효 기록이 있는 비율. 전체 / 전반부 2일 이상 / 1일."""
    seen = {m["mistake_id"] for m in _valid(mistakes) if m["date"] >= since}
    groups = {"all": frozen,
              "multi_day": [f for f in frozen if int(f["n_days"]) >= 2],
              "single_day": [f for f in frozen if int(f["n_days"]) < 2]}
    out = []
    for g, rows in groups.items():
        hit = sorted(f["mistake_id"] for f in rows if f["mistake_id"] in seen)
        n = len(rows)
        lo, hi = wilson(len(hit), n)
        out.append({"group": g, "k": len(hit), "n": n, "rate": round(len(hit) / n, 3) if n else 0.0,
                    "ci_low": lo, "ci_high": hi, "ids": " ".join(hit)})
    return out


def id_types(mistakes: list[dict]) -> dict[str, tuple[str, str]]:
    """ID마다 (영역, 문법 세부 묶음). 영역은 AI 표시를 정규화한 다수결, _spelling으로 끝나면 철자."""
    votes: dict[str, Counter] = {}
    for m in _valid(mistakes):
        votes.setdefault(m["mistake_id"], Counter())[AREA_NORM.get(m["area"].strip().lower(),
                                                                  AREA_NORM.get(m["area"].strip(), "expression"))] += 1
    out = {}
    for mid, c in votes.items():
        area = "spelling" if mid.endswith("_spelling") else c.most_common(1)[0][0]
        if mid in GROUP_OF:
            area = "grammar"
        out[mid] = (area, GROUP_OF.get(mid, "other") if area == "grammar" else "")
    return out


def recurrence_by_type(mistakes: list[dict]) -> list[dict]:
    """영역별·문법 묶음별: ID 수, 2일 이상 나온 ID 수와 비율, 기록 수."""
    valid = _valid(mistakes)
    types = id_types(mistakes)
    days: dict[str, set] = {}
    records = Counter()
    for m in valid:
        days.setdefault(m["mistake_id"], set()).add(m["date"])
        records[m["mistake_id"]] += 1
    out = []
    for level, key in (("area", 0), ("grammar", 1)):
        names = AREA_KO if level == "area" else GRAMMAR_KO
        for g in names:
            ids = [mid for mid, t in types.items() if t[key] == g and (level == "area" or t[0] == "grammar")]
            if not ids:
                continue
            multi = sorted(mid for mid in ids if len(days[mid]) >= 2)
            out.append({"level": level, "group": g, "n_ids": len(ids), "n_multi_day": len(multi),
                        "multi_share": round(len(multi) / len(ids), 3), "n_records": sum(records[i] for i in ids),
                        "multi_ids": " ".join(multi)})
    return out


def survival_rows(mistakes: list[dict], days: list[str]) -> list[dict]:
    """ID마다 처음 나온 근무일부터 다음에 다시 나온 근무일까지의 간격(근무일 수).
    다시 안 나왔으면 마지막 근무일까지를 관측 시간으로 두고 event=0. 마지막 날 처음 나온 ID는 뺀다."""
    idx = {d: i for i, d in enumerate(days)}
    seen: dict[str, set] = {}
    for m in _valid(mistakes):
        if m["date"] in idx:
            seen.setdefault(m["mistake_id"], set()).add(idx[m["date"]])
    out = []
    for mid, s in sorted(seen.items()):
        first, rest = min(s), sorted(s)[1:]
        if rest:
            out.append({"mistake_id": mid, "first_date": days[first], "time": rest[0] - first, "event": 1})
        elif first < len(days) - 1:
            out.append({"mistake_id": mid, "first_date": days[first], "time": len(days) - 1 - first, "event": 0})
    return out


def kaplan_meier(rows: list[dict]) -> list[dict]:
    """S(t) = '처음 나온 뒤 t근무일까지 아직 다시 안 나온 비율'. 관측 시간마다 한 줄."""
    out = [{"time": 0, "at_risk": len(rows), "events": 0, "censored": 0, "survival": 1.0}]
    s = 1.0
    for t in sorted({r["time"] for r in rows}):
        at_risk = sum(r["time"] >= t for r in rows)
        events = sum(r["time"] == t and r["event"] for r in rows)
        censored = sum(r["time"] == t and not r["event"] for r in rows)
        s *= 1 - events / at_risk
        out.append({"time": t, "at_risk": at_risk, "events": events, "censored": censored, "survival": round(s, 3)})
    return out


def _write(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


# ---------- 그래프 ----------
INK, MUTED, GRID, SURFACE, BLUE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb", "#2a78d6"


def _plt():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False})
    return matplotlib, plt


def _style(ax, pct_x=False):
    ax.set_facecolor(SURFACE)
    ax.tick_params(length=0, labelsize=9.5, colors=MUTED)
    for s in ("top", "right", "bottom"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    if pct_x:
        import matplotlib.ticker as mt

        ax.xaxis.set_major_formatter(mt.PercentFormatter(1.0, decimals=0))


def _hbar(ax, labels, values, notes, lows=None, highs=None):
    y = list(range(len(labels)))[::-1]
    ax.barh(y, values, color=BLUE, height=0.55, zorder=2)
    if lows is not None:
        ax.errorbar(values, y, xerr=[[v - lo for v, lo in zip(values, lows)], [hi - v for v, hi in zip(values, highs)]],
                    fmt="none", ecolor=INK, elinewidth=1, capsize=3, zorder=3)
    for yi, v, note, hi in zip(y, values, notes, highs or values):
        ax.annotate(note, (max(v, hi), yi), textcoords="offset points", xytext=(6, 0), va="center", fontsize=9.5,
                    color=INK)
    ax.set_yticks(y, labels, fontsize=10, color=INK)
    ax.set_xlim(0, 1.15)


def plot_reappearance(rows: list[dict], path: Path, period: str) -> None:
    _, plt = _plt()
    fig, ax = plt.subplots(figsize=(8.5, 3.2), facecolor=SURFACE)
    _style(ax, pct_x=True)
    _hbar(ax, [REAPPEAR_KO[r["group"]] for r in rows], [r["rate"] for r in rows],
          [f"{r['rate']:.0%}  ({r['k']}/{r['n']})" for r in rows],
          [r["ci_low"] for r in rows], [r["ci_high"] for r in rows])
    ax.set_title(f"전반부 실수 ID가 후반부({period})에 다시 나온 비율", loc="left", fontsize=12.5, color=INK, pad=12,
                 fontweight="bold")
    fig.text(0.01, 0.02, "막대 끝 선 = 95% 구간 (Wilson) · 후반부 진행 중인 중간값", fontsize=9, color=MUTED)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def plot_by_type(rows: list[dict], path: Path, period: str) -> None:
    _, plt = _plt()
    area = [r for r in rows if r["level"] == "area"]
    gram = [r for r in rows if r["level"] == "grammar"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.2), facecolor=SURFACE,
                             gridspec_kw={"width_ratios": [len(area), len(gram)]})
    for ax, rs, names, title in ((axes[0], area, AREA_KO, "영역별"), (axes[1], gram, GRAMMAR_KO, "문법 세부 묶음별")):
        _style(ax, pct_x=True)
        _hbar(ax, [names[r["group"]] for r in rs], [r["multi_share"] for r in rs],
              [f"{r['multi_share']:.0%}  ({r['n_multi_day']}/{r['n_ids']}개 ID)" for r in rs])
        ax.set_title(title, loc="left", fontsize=11.5, color=INK, pad=10)
    fig.suptitle(f"실수 ID 중 2일 이상 나온 비율 ({period})", x=0.01, ha="left", fontsize=13.5, color=INK,
                 fontweight="bold")
    fig.text(0.01, 0.02, "괄호 = 2일 이상 나온 ID / 전체 ID · 늦게 처음 나온 ID는 관측일이 짧아 비율이 낮게 나오는 편 "
             "→ 생존 곡선으로 보완", fontsize=9, color=MUTED)
    fig.tight_layout(rect=(0, 0.06, 1, 0.93))
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def plot_survival(curves: list[tuple[str, list[dict], list[dict]]], path: Path, period: str) -> None:
    """작은 그래프 여러 개 (전체 / 문법 / 문법 외). 계단선 + 관측 중단 표시(세로 눈금)."""
    _, plt = _plt()
    import matplotlib.ticker as mt

    tmax = max(r["time"] for _, rows, _ in curves for r in rows)
    fig, axes = plt.subplots(1, len(curves), figsize=(5 * len(curves), 4.2), facecolor=SURFACE, sharey=True)
    for ax, (title, rows, km) in zip(axes, curves):
        ax.set_facecolor(SURFACE)
        xs = [p["time"] for p in km] + [tmax]
        ys = [p["survival"] for p in km] + [km[-1]["survival"]]
        ax.step(xs, ys, where="post", color=BLUE, linewidth=2, zorder=3)
        sv = {p["time"]: p["survival"] for p in km}
        cens = [t for t in sorted({r["time"] for r in rows if not r["event"]})]
        ax.plot(cens, [sv[t] for t in cens], linestyle="none", marker="|", markersize=11, color=INK,
                markeredgewidth=1.3, zorder=4)
        n, ev = len(rows), sum(r["event"] for r in rows)
        last = km[-1]["survival"]
        ax.annotate(f"{last:.0%}", (tmax, last), textcoords="offset points", xytext=(6, 0), va="center", fontsize=10,
                    color=INK, fontweight="bold")
        ax.set_title(f"{title}   ID {n}개 · 재발 {ev}개", loc="left", fontsize=11.5, color=INK, pad=10)
        ax.set_xlim(0, tmax + 0.6)
        ax.set_ylim(0, 1.05)
        ax.set_xticks(range(0, tmax + 1))
        ax.set_xlabel("처음 나온 뒤 지난 근무일", fontsize=9.5, color=MUTED)
        ax.yaxis.set_major_formatter(mt.PercentFormatter(1.0, decimals=0))
        ax.tick_params(length=0, labelsize=9.5, colors=MUTED)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
    fig.suptitle(f"아직 다시 안 나온 실수 ID의 비율 (Kaplan–Meier, {period})", x=0.01, ha="left", fontsize=13.5,
                 color=INK, fontweight="bold")
    fig.text(0.01, 0.02, "세로 눈금 = 관측 중단 (그 근무일까지 다시 안 나왔고 이후 아직 못 봄) · 마지막 날 처음 나온 ID는 제외",
             fontsize=9, color=MUTED)
    fig.tight_layout(rect=(0, 0.05, 1, 0.92))
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def main() -> None:
    sessions, mistakes = _read(OUT / "sessions.csv"), _read(OUT / "mistakes.csv")
    frozen = _read(FROZEN)
    days = sorted({s["date"] for s in sessions})
    last = days[-1]
    period = f"{int(days[0][5:7])}/{int(days[0][8:])}~{int(last[5:7])}/{int(last[8:])}"
    second = f"{int(SECOND_HALF_START[5:7])}/{int(SECOND_HALF_START[8:])}~{int(last[5:7])}/{int(last[8:])}"

    re_rows = reappearance(frozen, mistakes)
    _write(OUT / "reappearance.csv", re_rows)
    n_second = sum(d >= SECOND_HALF_START for d in days)
    print(f"[1. 재등장] 전반부(~{FIRST_HALF_END}) ID 중 후반부 {second} ({n_second}근무일)에 다시 나온 비율")
    for r in re_rows:
        print(f"  {REAPPEAR_KO[r['group']]:<10} {r['k']:>2}/{r['n']:<2} = {r['rate']:.0%}  "
              f"(95% {r['ci_low']:.0%}~{r['ci_high']:.0%})  {r['ids']}")
    new_second = {m["mistake_id"] for m in _valid(mistakes) if m["date"] >= SECOND_HALF_START}
    frozen_ids = {f["mistake_id"] for f in frozen}
    print(f"  후반부에 나온 ID {len(new_second)}개 중 전반부에 없던 새 ID {len(new_second - frozen_ids)}개")

    by_type = recurrence_by_type(mistakes)
    _write(OUT / "repeat_by_type.csv", by_type)
    print(f"\n[2. 유형별] 2일 이상 나온 ID 비율 ({period})")
    for r in by_type:
        name = (AREA_KO if r["level"] == "area" else GRAMMAR_KO)[r["group"]]
        indent = "  " if r["level"] == "area" else "    └ "
        print(f"{indent}{name:<10} {r['n_multi_day']:>2}/{r['n_ids']:<2} = {r['multi_share']:.0%}  "
              f"기록 {r['n_records']:>3}건  {r['multi_ids']}")

    surv = survival_rows(mistakes, days)
    types = id_types(mistakes)
    for r in surv:
        r["area"], r["grammar_group"] = types[r["mistake_id"]]
    _write(OUT / "survival.csv", surv)
    curves = []
    for title, keep in (("전체", lambda r: True), ("문법", lambda r: r["area"] == "grammar"),
                        ("문법 외 (어휘·표현·철자)", lambda r: r["area"] != "grammar")):
        rows = [r for r in surv if keep(r)]
        curves.append((title, rows, kaplan_meier(rows)))
    print(f"\n[3. 생존 분석] 근무일 {len(days)}일 ({period}), 마지막 날 처음 나온 ID 제외")
    for title, rows, km in curves:
        steps = "  ".join(f"t{p['time']}:{p['survival']:.0%}(위험{p['at_risk']})" for p in km)
        print(f"  {title:<14} ID {len(rows)} · 재발 {sum(r['event'] for r in rows)}   {steps}")

    plot_reappearance(re_rows, FIG / "a_reappearance.png", second)
    plot_by_type(by_type, FIG / "a_by_type.png", period)
    plot_survival(curves, FIG / "a_survival.png", period)
    print(f"\n그래프: {FIG / 'a_reappearance.png'}, a_by_type.png, a_survival.png")


if __name__ == "__main__":
    main()
