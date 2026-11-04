"""첫 화면: 오늘의 모드 카드 4개, 대화 시작 버튼, 이번 주 기록."""

from datetime import date, datetime, timedelta

import customtkinter as ctk

from talk.planner import get_plan
from talk.reports import goal_progress
from talk.ui.theme import C, MODE_LABELS, button, card, font, label

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
LONG_ABSENCE_DAYS = 3


def greeting_text(now: datetime) -> str:
    if 5 <= now.hour < 11:
        return "좋은 아침이에요 👋"
    if 11 <= now.hour < 17:
        return "좋은 오후예요 👋"
    return "좋은 저녁이에요 👋"


class StartView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=C["bg"], corner_radius=0)
        self.app = app
        self.selected_mode = "daily"
        self._picked: tuple[date, str] | None = None  # 사용자가 직접 고른 모드(그날만 유지)
        self.day_marks: list[str] = []

        self.greeting = label(self, "", 18, "bold")
        self.greeting.pack(anchor="w", padx=24, pady=(22, 12))
        self.banner = ctk.CTkButton(self, text="", height=36, corner_radius=8, font=font(13, "bold"),
                                    fg_color=C["help_chip"], hover_color=C["help_bg"], text_color=C["help_fg"])
        self._grid_anchor = None

        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="x", padx=24)
        self._grid_anchor = grid
        grid.grid_columnconfigure((0, 1), weight=1, uniform="m")
        self.cards = {}
        for i, mode in enumerate(MODE_LABELS):
            c = card(grid, border_width=2, border_color=C["panel"], height=86)
            c.grid(row=i // 2, column=i % 2, sticky="nsew", padx=5, pady=5)
            c.title_label = label(c, MODE_LABELS[mode], 15, "bold")
            c.title_label.pack(anchor="w", padx=16, pady=(14, 2))
            c.topic_label = label(c, "", 12, color=C["muted"], wraplength=330, justify="left")
            c.topic_label.pack(anchor="w", padx=16, pady=(0, 14))
            for w in (c, c.title_label, c.topic_label):
                w.bind("<Button-1>", lambda e, m=mode: self.pick(m))
            self.cards[mode] = c

        self.start_button = button(self, "▶ 대화 시작", self.start, primary=True, height=44)
        self.start_button.configure(font=font(15, "bold"))
        self.start_button.pack(fill="x", padx=29, pady=(10, 18))

        label(self, "이번 주", 12, color=C["muted"]).pack(anchor="w", padx=29)
        week = ctk.CTkFrame(self, fg_color="transparent")
        week.pack(anchor="w", padx=29, pady=(4, 6))
        self.day_boxes = []
        for name in WEEKDAYS:
            b = ctk.CTkLabel(week, text=name, width=34, height=34, corner_radius=7, font=font(12),
                             fg_color=C["track"], text_color=C["muted"])
            b.pack(side="left", padx=3)
            self.day_boxes.append(b)
        self.progress = label(self, "", 13, color=C["muted"])
        self.progress.pack(anchor="w", padx=29)
        self.refresh()

    def refresh(self) -> None:
        store = self.app.services.store
        today = date.today()
        plan = get_plan(store, today)
        self.selected_mode = plan.recommended
        sessions = [s for s in store.list_sessions() if s.messages]
        absent = sessions and (today - date.fromisoformat(sessions[-1].date)).days > LONG_ABSENCE_DAYS
        hello = "다시 와서 반가워요 👋" if absent else greeting_text(datetime.now())
        self.greeting.configure(text=f"{hello}  · 오늘 추천: {MODE_LABELS[plan.recommended]}")
        for mode, c in self.cards.items():
            c.topic_label.configure(text=plan.topics[mode])
        picked = self._picked[1] if self._picked and self._picked[0] == today else None
        self.select(picked or plan.recommended)

        monday = today - timedelta(days=today.weekday())
        active = {s.date for s in sessions}
        self.day_marks = []
        for i, box in enumerate(self.day_boxes):
            d = monday + timedelta(days=i)
            mark = "done" if d.isoformat() in active else ""
            self.day_marks.append(mark)
            box.configure(fg_color=C["done"] if mark else C["track"],
                          text_color=C["fix_fg"] if mark else C["muted"])
            box.configure(text=WEEKDAYS[i] + ("•" if d == today else ""))
        done, goal = goal_progress(store, today.isoformat(), self.app.services.settings)
        self.progress.configure(text=f"오늘 {done} / {goal}분")

    def show_banner(self, text: str, on_click) -> None:
        def click():
            self.banner.pack_forget()
            on_click()

        self.banner.configure(text=text, command=click)
        self.banner.pack(fill="x", padx=29, pady=(0, 10), before=self._grid_anchor)

    def pick(self, mode: str) -> None:
        self._picked = (date.today(), mode)
        self.select(mode)

    def select(self, mode: str) -> None:
        self.selected_mode = mode
        for m, c in self.cards.items():
            c.configure(border_color=C["accent"] if m == mode else C["panel"])

    def start(self) -> None:
        if not self.app.services.settings.api_key:
            self.app.show("settings")
            self.app.views["settings"].status.configure(text="Gemini API 키를 먼저 넣어 주세요", text_color=C["warn"])
            return
        self.app.start_chat(self.selected_mode)
