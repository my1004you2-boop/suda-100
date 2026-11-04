"""기록 화면: 지난 대화 목록과 다시 보기(읽기 전용)."""

from datetime import datetime

import customtkinter as ctk

from talk.ui.chat_view import render_message
from talk.ui.theme import C, MODE_LABELS, font, label


def session_line(s) -> str:
    t = datetime.fromisoformat(s.started)
    return f"{t.month}월 {t.day}일 {t:%H:%M} · {MODE_LABELS[s.mode]} · {s.topic} · {s.seconds // 60}분"


class HistoryView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=C["bg"], corner_radius=0)
        self.app = app
        self.items: list[ctk.CTkButton] = []
        self.cards = []
        self.opened: str | None = None
        label(self, "기록", 18, "bold").pack(anchor="w", padx=24, pady=(20, 8))
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)
        self.list = ctk.CTkScrollableFrame(body, fg_color=C["side"], corner_radius=8, width=290)
        self.list.grid(row=0, column=0, sticky="ns", padx=(0, 8))
        self.detail = ctk.CTkScrollableFrame(body, fg_color=C["bg"], corner_radius=0)
        self.detail.grid(row=0, column=1, sticky="nsew")

    def refresh(self) -> None:
        for w in self.list.winfo_children() + self.detail.winfo_children():
            w.destroy()
        self.items, self.cards, self.opened = [], [], None
        sessions = [s for s in self.app.services.store.list_sessions() if s.messages][::-1]
        if not sessions:
            label(self.detail, "아직 대화 기록이 없어요", 14, color=C["muted"]).pack(pady=40)
            return
        for s in sessions:
            b = ctk.CTkButton(self.list, text=session_line(s), anchor="w", height=34, corner_radius=6,
                              font=font(12), fg_color="transparent", hover_color=C["side_hover"],
                              text_color=C["muted"], command=lambda sid=s.id: self.open(sid))
            b.session_id = s.id
            b.pack(fill="x", padx=4, pady=1)
            self.items.append(b)
        self.open(sessions[0].id)

    def open(self, session_id: str) -> None:
        for w in self.detail.winfo_children():
            w.destroy()
        self.cards = []
        self.opened = session_id
        for b in self.items:
            on = b.session_id == session_id
            b.configure(fg_color=C["panel"] if on else "transparent", text_color=C["fg"] if on else C["muted"])
        speak = self.app.views["chat"].speak if self.app.services.speech_enabled else None
        for msg in self.app.services.store.load_session(session_id).messages:
            _, cards = render_message(self.detail, msg, speak)
            self.cards += cards
        self.detail._parent_canvas.yview_moveto(0.0)
