"""일일 리포트 화면."""

from datetime import date

import customtkinter as ctk

from talk.reports import daily_dates, load_daily
from talk.ui.theme import C, MODE_LABELS, card, font, label

WEEKDAYS = "월화수목금토일"


def date_title(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.month}월 {d.day}일 ({WEEKDAYS[d.weekday()]})"


def short_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.month}월 {d.day}일"


class DailyView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=C["bg"], corner_radius=0)
        self.app = app
        self.dates: dict[str, str] = {}
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=24, pady=(20, 8))
        label(top, "일일 리포트", 18, "bold").pack(side="left")
        self.date_var = ctk.StringVar()
        self.date_menu = ctk.CTkOptionMenu(top, values=[""], variable=self.date_var, font=font(13), width=150,
                                           fg_color=C["panel"], button_color=C["panel"],
                                           command=lambda v: self.render(self.dates.get(v)))
        self.date_menu.pack(side="right")
        self.body = ctk.CTkScrollableFrame(self, fg_color=C["bg"], corner_radius=0)
        self.body.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def refresh(self) -> None:
        dates = daily_dates(self.app.services.store)
        self.dates = {date_title(d): d for d in dates}
        if dates:
            self.date_menu.configure(values=list(self.dates))
            self.date_var.set(date_title(dates[0]))
            self.date_menu.pack(side="right")
        else:
            self.date_menu.pack_forget()
        self.render(dates[0] if dates else None)

    def render(self, iso: str | None) -> None:
        for w in self.body.winfo_children():
            w.destroy()
        report = load_daily(self.app.services.store, iso) if iso else None
        if not report:
            label(self.body, "아직 리포트가 없어요. 오늘 첫 대화를 시작해 볼까요?", 14, color=C["muted"]).pack(pady=40)
            return

        modes = " · ".join(dict.fromkeys(MODE_LABELS[s["mode"]] for s in report["sessions"]))
        topics = " · ".join(dict.fromkeys(s["topic"] for s in report["sessions"]))
        label(self.body, f"{date_title(report['date'])} · {modes} · {topics}", 15, wraplength=700,
              justify="left").pack(anchor="w", padx=12, pady=(4, 10))

        stats = ctk.CTkFrame(self.body, fg_color="transparent")
        stats.pack(fill="x", padx=8)
        stats.grid_columnconfigure((0, 1, 2), weight=1, uniform="s")
        for i, (num, name) in enumerate([(f"{report['seconds'] // 60}분", "대화 시간"),
                                         (str(report["user_messages"]), "내가 한 말"),
                                         (str(len(report["learned"])), "원어민 표현")]):
            box = card(stats)
            box.grid(row=0, column=i, sticky="nsew", padx=4)
            label(box, num, 20, "bold", mono=True).pack(pady=(10, 0))
            label(box, name, 12, color=C["muted"]).pack(pady=(0, 10))

        if report["learned"]:
            box = self._section("오늘 배운 원어민 표현")
            for item in report["learned"]:
                row = ctk.CTkFrame(box, fg_color="transparent")
                row.pack(fill="x", padx=14, pady=2)
                label(row, item["original"], 12, color=C["muted"], wraplength=640, justify="left").pack(anchor="w")
                label(row, "→ " + item["native"], 13, "bold", color=C["fix_em"], wraplength=640,
                      justify="left").pack(anchor="w")
        if report["repeated"]:
            box = self._section("🔁 또 나온 표현 (지난번에도 나왔어요)")
            for r in report["repeated"]:
                label(box, f"\"{r['original']}\" · {r['count']}번째 · 처음 {short_date(r['first_seen'])}", 13,
                      color=C["repeat"], wraplength=640, justify="left").pack(anchor="w", padx=14, pady=2)
                label(box, "→ " + r["native"], 12, color=C["fix_em"]).pack(anchor="w", padx=28, pady=(0, 4))
        if report["now_correct"]:
            box = self._section("✨ 이제 맞게 쓴 표현")
            for r in report["now_correct"]:
                label(box, f"\"{r['native']}\"", 13, color=C["fix_em"]).pack(anchor="w", padx=14, pady=2)

    def _section(self, title: str) -> ctk.CTkFrame:
        box = card(self.body)
        box.pack(fill="x", padx=12, pady=(12, 0))
        label(box, title, 12, color=C["muted"]).pack(anchor="w", padx=14, pady=(10, 4))
        ctk.CTkFrame(box, fg_color="transparent", height=4).pack(side="bottom")
        return box
