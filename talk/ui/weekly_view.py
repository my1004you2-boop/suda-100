"""주간 평가서 화면."""

import customtkinter as ctk

from talk.reports import format_score, week_label, weekly_ids
from talk.ui.theme import C, card, font, label

SCORED = [("sincerity", "성실도"), ("willpower", "의지력"), ("speaking", "회화력"), ("understanding", "교정 이해력"),
          ("leadership", "대화 주도력")]
NO_TARGETS = "이번 주는 연습 대상이 없었어요"


class WeeklyView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=C["bg"], corner_radius=0)
        self.app = app
        self.weeks: dict[str, str] = {}
        self.shown: str | None = None
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=24, pady=(20, 8))
        label(top, "주간 평가", 18, "bold").pack(side="left")
        self.week_var = ctk.StringVar()
        self.week_menu = ctk.CTkOptionMenu(top, values=[""], variable=self.week_var, font=font(13), width=200,
                                           fg_color=C["panel"], button_color=C["panel"],
                                           command=lambda v: self.render(self.weeks.get(v)))
        self.body = ctk.CTkScrollableFrame(self, fg_color=C["bg"], corner_radius=0)
        self.body.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def refresh(self) -> None:
        ids = weekly_ids(self.app.services.store)
        self.weeks = {week_label(w): w for w in ids}
        if ids:
            self.week_menu.configure(values=list(self.weeks))
            self.week_var.set(week_label(ids[0]))
            self.week_menu.pack(side="right")
        else:
            self.week_menu.pack_forget()
        self.render(ids[0] if ids else None)

    def render(self, week: str | None) -> None:
        for w in self.body.winfo_children():
            w.destroy()
        self.shown = week
        data = self.app.services.store.load_json(f"weekly/{week}.json", None) if week else None
        if not data:
            label(self.body, "첫 평가서는 이번 주가 끝나면 도착해요", 14, color=C["muted"]).pack(pady=40)
            return

        label(self.body, week_label(week), 15, "bold").pack(anchor="w", padx=12, pady=(4, 8))
        letter = card(self.body)
        letter.pack(fill="x", padx=12)
        label(letter, data.get("letter", ""), 13, wraplength=680, justify="left").pack(anchor="w", padx=16, pady=14)
        before, after = data.get("level_before"), data.get("level_after")
        if isinstance(before, (int, float)) and isinstance(after, (int, float)) and after > before:
            label(self.body, f"🌱 다음 주부터 대화가 조금 더 자연스러워져요 (레벨 {before:.1f} → {after:.1f})", 12,
                  color=C["fix_em"]).pack(anchor="w", padx=14, pady=(8, 0))

        grid = ctk.CTkFrame(self.body, fg_color="transparent")
        grid.pack(fill="x", padx=8, pady=(8, 0))
        grid.grid_columnconfigure((0, 1), weight=1, uniform="w")
        scores, reasons = data.get("scores", {}), data.get("reasons", {})
        items = []
        for key, name in SCORED:
            reason = reasons.get(key, "")
            if key == "understanding" and scores.get(key) is None:
                reason = NO_TARGETS
            items.append((name, format_score(scores.get(key)), reason))
        items += [("부족한 점", "", data.get("weak_points", "")), ("다음 주 방안", "", data.get("next_plan", ""))]
        for i, (name, score, text) in enumerate(items):
            box = card(grid)
            box.grid(row=i // 2, column=i % 2, sticky="nsew", padx=4, pady=4)
            head = ctk.CTkFrame(box, fg_color="transparent")
            head.pack(fill="x", padx=14, pady=(10, 2))
            label(head, name, 13, "bold", color=C["fix_fg"]).pack(side="left")
            if score:
                label(head, score, 13, "bold", color=C["fix_em"], mono=True).pack(side="right")
            label(box, text, 12, color=C["muted"], wraplength=300, justify="left").pack(anchor="w", padx=14,
                                                                                       pady=(0, 12))
