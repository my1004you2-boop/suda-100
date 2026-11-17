"""9일차: 전반·후반 비교, 입력 방식 비교(C1), AI 판정 검수(C2).

실행 (회화앱 폴더에서, prep·metrics 다음에):
    python -m analysis.final_compare

1. 전반부(11/5~11/11) vs 후반부(11/12~) 지표 비교. 차이의 95% 구간은 **대화 단위 부트스트랩**
   (같은 대화 안의 메시지끼리는 비슷하므로 메시지가 아니라 대화를 통째로 다시 뽑는다).
2. 11/4를 뺀 생존 곡선 (11/4는 채점 모델이 달랐을 수 있음 → 결과가 11/4에 기대는지 점검).
3. 입력 방식 비교: 음성 vs 타자. 받아쓰기 오류로 생긴 실수(analysis/stt_flags.csv, 사람이 표시)를 뺀 값도.
4. AI 판정 검수: analysis/audit.csv가 없으면 전반·후반 15개씩 무작위로 뽑아 만든다 (한 번만, 덮어쓰지 않음).
   사람이 h_ 칸을 채우면 다시 실행했을 때 일치율을 계산한다. audit.csv·stt_flags.csv는 원문이 있어 git 제외.

만드는 파일: analysis/out/half_compare.csv, voice_compare.csv, audit_summary.csv, figures/c_half_compare.png
"""

import csv
import random
from pathlib import Path

from analysis.balance import FIRST_HALF_END
from analysis.interim import AI_SINCE, FIG, MODE_KO, by_group
from analysis.metrics import OUT, ROOT, _read, _t
from analysis.mistake_repeat import id_types, kaplan_meier, survival_rows
from analysis.speech_change import LONG_MIN, SHORT_MAX, _tokens, msttr

AUDIT = ROOT / "analysis" / "audit.csv"
STT = ROOT / "analysis" / "stt_flags.csv"
SEED = 20261117
AUDIT_COLS = ["audit_id", "half", "date", "session_id", "msg_idx", "mode", "via_voice", "text", "ai_corrected",
              "ai_n_mistakes", "ai_mistakes", "ai_user_led", "ai_question",
              "h_false_mistakes", "h_missed", "h_should_correct", "h_lead_ok", "h_question_ok", "h_note"]


def half_of(date: str) -> str:
    if date < AI_SINCE:
        return ""
    return "first" if date <= FIRST_HALF_END else "second"


def cluster_bootstrap(first: list[dict], second: list[dict], stat, n: int = 2000, seed: int = SEED) -> dict:
    """stat(메시지 목록)의 후반부 - 전반부 차이. 대화(session_id) 단위로 다시 뽑아 95% 구간."""
    def by_session(ms):
        out: dict[str, list] = {}
        for x in ms:
            out.setdefault(x["session_id"], []).append(x)
        return list(out.values())

    a, b = by_session(first), by_session(second)
    rng = random.Random(seed)
    diffs = []
    for _ in range(n):
        ra = [x for s in rng.choices(a, k=len(a)) for x in s]
        rb = [x for s in rng.choices(b, k=len(b)) for x in s]
        va, vb = stat(ra), stat(rb)
        if va is not None and vb is not None:
            diffs.append(vb - va)
    diffs.sort()
    fa, fb = stat(first), stat(second)
    return {"first": round(fa, 3), "second": round(fb, 3), "diff": round(fb - fa, 3),
            "ci_low": round(diffs[int(0.025 * len(diffs))], 3), "ci_high": round(diffs[int(0.975 * len(diffs)) - 1], 3)}


def _share(col):
    return lambda ms: sum(_t(x[col]) for x in ms) / len(ms) if ms else None


METRICS = [  # (이름, 한국어, 비율인지, 계산)
    ("avg_words", "메시지당 평균 단어", False, lambda ms: sum(int(x["n_words"]) for x in ms) / len(ms) if ms else None),
    ("short_share", f"짧은 답 ({SHORT_MAX}단어 이하)", True,
     lambda ms: sum(int(x["n_words"]) <= SHORT_MAX for x in ms) / len(ms) if ms else None),
    ("long_share", f"긴 문장 ({LONG_MIN}단어 이상)", True,
     lambda ms: sum(int(x["n_words"]) >= LONG_MIN for x in ms) / len(ms) if ms else None),
    ("msttr50", "어휘 다양성 (MSTTR)", False, lambda ms: (msttr(_tokens(ms))[0] or None)),
    ("corrected_rate", "교정받은 비율", True, _share("corrected")),
    ("mistakes_per_msg", "메시지당 실수", False,
     lambda ms: sum(int(x["n_valid"]) for x in ms) / len(ms) if ms else None),
    ("lead_rate", "주도율", True,
     lambda ms: sum(_t(x["user_led"]) or _t(x["user_asked_question"]) for x in ms) / len(ms) if ms else None),
    ("question_rate", "질문 비율", True, _share("user_asked_question")),
]


def _valid_count(messages: list[dict], mistakes: list[dict]) -> None:
    """메시지마다 유효한 실수 수(n_valid)를 붙인다."""
    cnt: dict[tuple, int] = {}
    for r in mistakes:
        if _t(r["valid"]):
            cnt[(r["session_id"], r["msg_idx"])] = cnt.get((r["session_id"], r["msg_idx"]), 0) + 1
    for x in messages:
        x["n_valid"] = cnt.get((x["session_id"], x["msg_idx"]), 0)


def voice_compare(messages: list[dict], mistakes: list[dict], stt: set) -> list[dict]:
    """음성/타자별 메시지 수, 길이, 교정 비율, 실수. _clean = 받아쓰기 오류 실수를 뺀 값
    (받아쓰기 오류 실수만 있던 메시지는 교정받지 않은 것으로 본다)."""
    per_msg: dict[tuple, list] = {}
    for r in mistakes:
        if _t(r["valid"]):
            per_msg.setdefault((r["session_id"], r["msg_idx"]), []).append((r["session_id"], r["msg_idx"]) in stt)
    out = []
    for name, flag in (("voice", "True"), ("typed", "False")):
        ms = [x for x in messages if x["via_voice"] == flag]
        if not ms:
            continue
        keys = [(x["session_id"], x["msg_idx"]) for x in ms]
        n_mk = sum(len(per_msg.get(k, [])) for k in keys)
        n_stt = sum(sum(per_msg.get(k, [])) for k in keys)
        clean = sum(_t(x["corrected"]) and not (per_msg.get(k) and all(per_msg[k])) for x, k in zip(ms, keys))
        out.append({"input": name, "n_msgs": len(ms), "n_sessions": len({x["session_id"] for x in ms}),
                    "avg_words": round(sum(int(x["n_words"]) for x in ms) / len(ms), 1),
                    "corrected_rate": round(sum(_t(x["corrected"]) for x in ms) / len(ms), 3),
                    "corrected_rate_clean": round(clean / len(ms), 3),
                    "mistakes": n_mk, "stt_mistakes": n_stt,
                    "mistakes_per_msg_clean": round((n_mk - n_stt) / len(ms), 2)})
    return out


def draw_audit(messages: list[dict], mistakes: list[dict], per_half: int = 15, seed: int = SEED) -> list[dict]:
    """전반·후반에서 per_half개씩 무작위 메시지. 같은 seed면 같은 표본."""
    mk: dict[tuple, list] = {}
    for r in mistakes:
        if _t(r["valid"]):
            mk.setdefault((r["session_id"], r["msg_idx"]), []).append(f"{r['original']} → {r['native']}")
    rng = random.Random(seed)
    out = []
    for half in ("first", "second"):
        pool = sorted((x for x in messages if half_of(x["date"]) == half),
                      key=lambda x: (x["session_id"], int(x["msg_idx"])))
        for x in sorted(rng.sample(pool, min(per_half, len(pool))), key=lambda x: (x["date"], x["session_id"])):
            k = (x["session_id"], x["msg_idx"])
            out.append({"half": half, "date": x["date"], "session_id": x["session_id"], "msg_idx": x["msg_idx"],
                        "mode": x.get("mode", ""), "via_voice": x["via_voice"], "text": x["text"],
                        "ai_corrected": x["corrected"], "ai_n_mistakes": len(mk.get(k, [])),
                        "ai_mistakes": " | ".join(mk.get(k, [])), "ai_user_led": x["user_led"],
                        "ai_question": x["user_asked_question"],
                        "h_false_mistakes": "", "h_missed": "", "h_should_correct": "", "h_lead_ok": "",
                        "h_question_ok": "", "h_note": ""})
    for i, r in enumerate(out, 1):
        r["audit_id"] = i
    return out


def audit_summary(rows: list[dict]) -> list[dict]:
    """채운 행만. false_mistake_share = AI 실수 기록 중 진짜 실수가 아닌 비율, missed_per_msg = 놓친 실수/메시지,
    *_agree = AI 판정과 사람 판정이 같은 비율."""
    out = []
    for half in ("first", "second", "all"):
        rs = [r for r in rows if r["h_should_correct"] and (half == "all" or r["half"] == half)]
        if not rs:
            continue
        n_ai = sum(int(r["ai_n_mistakes"]) for r in rs)
        out.append({"half": half, "n": len(rs), "ai_mistakes": n_ai,
                    "false_mistake_share": round(sum(int(r["h_false_mistakes"]) for r in rs) / n_ai, 3) if n_ai else "",
                    "missed_per_msg": round(sum(int(r["h_missed"]) for r in rs) / len(rs), 2),
                    "correct_agree": round(sum(_t(r["ai_corrected"]) == (r["h_should_correct"] == "Y")
                                               for r in rs) / len(rs), 3),
                    "lead_agree": round(sum(r["h_lead_ok"] == "Y" for r in rs) / len(rs), 3),
                    "question_agree": round(sum(r["h_question_ok"] == "Y" for r in rs) / len(rs), 3)})
    return out


def _write(path: Path, rows: list[dict], cols: list[str] | None = None) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols or list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def plot_half_compare(rows: list[dict], path: Path) -> None:
    """비율 지표만: 전반부 점 → 후반부 점 (아령 그래프), 오른쪽에 차이와 95% 구간."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mt

    plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False})
    ink, muted, grid, surface, blue = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb", "#2a78d6"
    rs = [r for r in rows if r["pct"]]
    fig, ax = plt.subplots(figsize=(10, 0.75 * len(rs) + 1.6), facecolor=surface)
    ax.set_facecolor(surface)
    for i, r in enumerate(reversed(rs)):
        ax.plot([r["first"], r["second"]], [i, i], color=grid, linewidth=3, zorder=1)
        ax.plot(r["first"], i, "o", markersize=9, markerfacecolor=surface, markeredgecolor=muted, markeredgewidth=1.8,
                zorder=2)
        ax.plot(r["second"], i, "o", markersize=9, color=blue, zorder=3)
        sig = r["ci_low"] > 0 or r["ci_high"] < 0
        ax.annotate(f"{r['diff'] * 100:+.0f}%p  ({r['ci_low'] * 100:+.0f}~{r['ci_high'] * 100:+.0f})" +
                    ("  ●" if sig else ""), (1.02, i), xycoords=("axes fraction", "data"), va="center", fontsize=9.5,
                    color=ink if sig else muted, fontweight="bold" if sig else "normal")
    ax.set_yticks(range(len(rs)), [r["label"] for r in reversed(rs)], fontsize=10, color=ink)
    ax.set_xlim(0, 0.85)
    ax.xaxis.set_major_formatter(mt.PercentFormatter(1.0, decimals=0))
    ax.tick_params(length=0, labelsize=9.5, colors=muted)
    ax.grid(axis="x", color=grid, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left", "bottom"):
        ax.spines[s].set_visible(False)
    ax.set_title("전반부(11/5~11/11, 속 빈 점) → 후반부(11/12~, 파란 점)", loc="left", fontsize=12.5, color=ink,
                 fontweight="bold", pad=12)
    fig.text(0.01, 0.02, "오른쪽 = 차이 (95% 구간, 대화 단위 부트스트랩) · ● = 구간이 0을 포함하지 않음", fontsize=9,
             color=muted)
    fig.tight_layout(rect=(0, 0.05, 0.8, 1))
    fig.savefig(path, dpi=150, facecolor=surface)
    plt.close(fig)


def main() -> None:
    sessions, messages, mistakes = (_read(OUT / f) for f in ("sessions.csv", "messages.csv", "mistakes.csv"))
    _valid_count(messages, mistakes)
    first = [x for x in messages if half_of(x["date"]) == "first"]
    second = [x for x in messages if half_of(x["date"]) == "second"]
    last = max(x["date"] for x in messages)

    rows = []
    print(f"[1. 전반부 vs 후반부] 메시지 {len(first)} vs {len(second)}, 대화 "
          f"{len({x['session_id'] for x in first})} vs {len({x['session_id'] for x in second})}  (후반부 ~{last})")
    for key, label, pct, fn in METRICS:
        r = {"metric": key, "label": label, "pct": pct, **cluster_bootstrap(first, second, fn)}
        rows.append(r)
        f = (lambda v: f"{v:.0%}") if pct else (lambda v: f"{v:g}")
        sig = "  ●" if r["ci_low"] > 0 or r["ci_high"] < 0 else ""
        d = (lambda v: f"{v * 100:+.0f}%p") if pct else (lambda v: f"{v:+.2f}")
        print(f"  {label:<18} {f(r['first']):>6} → {f(r['second']):>6}   차이 {d(r['diff'])} "
              f"(95% {d(r['ci_low'])}~{d(r['ci_high'])}){sig}")
    _write(OUT / "half_compare.csv", rows)
    plot_half_compare(rows, FIG / "c_half_compare.png")

    print("\n[2. 생존 분석: 11/4 포함 vs 제외]")
    for name, since in (("11/4 포함", "2026-11-04"), ("11/4 제외", AI_SINCE)):
        days = sorted({s["date"] for s in sessions if s["date"] >= since})
        mk = [r for r in mistakes if r["date"] >= since]
        surv = survival_rows(mk, days)
        types = id_types(mk)
        for title, keep in (("전체", lambda r: True), ("문법", lambda r: types[r["mistake_id"]][0] == "grammar"),
                            ("문법 외", lambda r: types[r["mistake_id"]][0] != "grammar")):
            rs = [r for r in surv if keep(r)]
            km = kaplan_meier(rs)
            at4 = [p["survival"] for p in km if p["time"] <= 4][-1]
            print(f"  {name}  {title:<5} ID {len(rs):>3} · 재발 {sum(r['event'] for r in rs):>2}  "
                  f"4근무일 뒤 안 나온 비율 {at4:.0%}  마지막 {km[-1]['survival']:.0%}")

    print("\n[3. 모드별 (11/5~)]")
    for r in by_group(sessions, messages, mistakes, "mode", since=AI_SINCE):
        print(f"  {MODE_KO.get(r['group'], r['group']):<6} 대화 {r['n_sessions']}  메시지 {r['n_msgs']:>3}  "
              f"단어 {r['avg_words']:>5}  교정 {float(r['corrected_rate']):.0%}  실수 {r['mistakes_per_msg']}  "
              f"주도 {float(r['lead_rate']):.0%}")
    stt_rows = _read(STT) if STT.exists() else []
    stt = {(r["session_id"], r["msg_idx"]) for r in stt_rows if r["stt"] == "yes"}
    vc = voice_compare([x for x in messages if x["date"] >= AI_SINCE], mistakes, stt)
    _write(OUT / "voice_compare.csv", vc)
    print(f"\n[3. 입력 방식 (11/5~)]  받아쓰기 오류 표시: 확실 {len(stt)}건, 애매 "
          f"{sum(r['stt'] == 'maybe' for r in stt_rows)}건")
    for r in vc:
        print(f"  {r['input']:<6} 대화 {r['n_sessions']}  메시지 {r['n_msgs']:>3}  단어 {r['avg_words']:>4}  "
              f"교정 {r['corrected_rate']:.0%} (받아쓰기 오류 빼면 {r['corrected_rate_clean']:.0%})  "
              f"실수 {r['mistakes']}건 중 받아쓰기 오류 {r['stt_mistakes']}건")

    if not AUDIT.exists():
        audit = draw_audit(messages, mistakes)
        _write(AUDIT, audit, AUDIT_COLS)
        print(f"\n[4. AI 판정 검수] 표본 {len(audit)}개를 새로 뽑았다: {AUDIT}  (h_ 칸을 채운 뒤 다시 실행)")
    else:
        summ = audit_summary(_read(AUDIT))
        if summ:
            _write(OUT / "audit_summary.csv", summ)
            print("\n[4. AI 판정 검수]  가짜 실수 비율 · 놓친 실수/메시지 · 교정 판정 일치 · 주도 일치 · 질문 일치")
            for r in summ:
                fm = f"{r['false_mistake_share']:.0%}" if r["false_mistake_share"] != "" else "-"
                print(f"  {r['half']:<6} n={r['n']:>2}  AI 실수 {r['ai_mistakes']:>2}건  {fm:>4}  {r['missed_per_msg']}  "
                      f"{r['correct_agree']:.0%}  {r['lead_agree']:.0%}  {r['question_agree']:.0%}")
        else:
            print(f"\n[4. AI 판정 검수] {AUDIT}의 h_ 칸이 비어 있다")
    print(f"\n그래프: {FIG / 'c_half_compare.png'}")


if __name__ == "__main__":
    main()
