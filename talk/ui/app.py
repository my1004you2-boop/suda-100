"""수다백단 앱 창: 왼쪽 메뉴와 화면 전환."""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

import customtkinter as ctk

from talk.config import APP_NAME, DATA_DIR, SETTINGS_PATH, Settings, load_settings
from talk.conversation import Conversation
from talk.llm import LLM, GeminiLLM
from talk.memory import load_memory
from talk.planner import get_plan
from talk.reports import current_level, finalize_session
from talk.startup import run_startup
from talk.store import Store
from talk.ui.chat_view import ChatView
from talk.ui.daily_view import DailyView
from talk.ui.history_view import HistoryView
from talk.ui.settings_view import SettingsView
from talk.ui.start_view import StartView
from talk.ui.weekly_view import WeeklyView
from talk.ui.theme import C, font, label
from talk.worker import Worker

MENU = [("start", "오늘 대화"), ("daily", "일일 리포트"), ("weekly", "주간 평가"), ("history", "기록"),
        ("settings", "설정")]


@dataclass
class Services:
    store: Store
    settings: Settings
    llm_factory: Callable[[Settings], LLM]
    speech_enabled: bool = True
    settings_path: Path = field(default=SETTINGS_PATH)
    run_startup: bool = True


class App(ctk.CTk):
    def __init__(self, services: Services):
        ctk.set_appearance_mode("dark")
        super().__init__(fg_color=C["bg"])
        self.services = services
        self.worker = Worker(self)
        self.current: str | None = None
        self.conversation = None
        self.has_mic = False
        if services.speech_enabled:
            self._setup_speech()
        self.title(APP_NAME)
        self.geometry("1000x680")
        self.minsize(860, 560)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        side = ctk.CTkFrame(self, fg_color=C["side"], corner_radius=0, width=130)
        side.grid(row=0, column=0, sticky="ns")
        side.grid_propagate(False)
        label(side, APP_NAME, 16, "bold").pack(anchor="w", padx=16, pady=(18, 14))
        self.menu_buttons = {}
        for name, text in MENU:
            b = ctk.CTkButton(side, text=text, anchor="w", height=34, corner_radius=7, font=font(13),
                              fg_color="transparent", hover_color=C["side_hover"], text_color=C["muted"],
                              command=lambda n=name: self.on_menu(n))
            b.pack(fill="x", padx=8, pady=2)
            self.menu_buttons[name] = b

        self.content = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        self.views = self.build_views()
        for view in self.views.values():
            view.grid(row=0, column=0, sticky="nsew")
        self.show("start")
        if services.run_startup:
            self.after(500, self.startup_jobs)

    def startup_jobs(self) -> None:
        """마무리 안 된 대화를 정리하고, 지난주 평가서를 쓴다(작업 스레드)."""
        if not self.services.settings.api_key:
            return
        llm, store, settings = self.make_llm(), self.services.store, self.services.settings
        active = self.conversation.session.id if self.conversation else None

        def done(new_weekly):
            if new_weekly:
                self.views["start"].show_banner("📬 지난주 평가서가 도착했어요", lambda: self.show("weekly"))
            if self.current in ("start", "daily"):
                self.views[self.current].refresh()

        self.worker.run(lambda: run_startup(llm, store, settings, active, date.today()), done, lambda e: None)

    def build_views(self) -> dict:
        return {
            "start": StartView(self.content, self),
            "chat": ChatView(self.content, self),
            "daily": DailyView(self.content, self),
            "weekly": WeeklyView(self.content, self),
            "history": HistoryView(self.content, self),
            "settings": SettingsView(self.content, self),
        }

    def _setup_speech(self) -> None:
        from talk.speech import Recorder, Transcriber, list_input_devices

        self.has_mic = bool(list_input_devices())
        self.recorder = Recorder(self.services.settings.mic_device)
        self.transcriber = Transcriber(self.services.settings.whisper_model)
        if self.has_mic:
            self.worker.run(self.transcriber.load, None, lambda e: None)  # 첫 실행엔 모델을 내려받는다

    def on_menu(self, name: str) -> None:
        if name == "start" and self.conversation is not None:
            name = "chat"
        self.show(name)

    def show(self, name: str) -> None:
        self.current = name
        view = self.views[name]
        view.refresh()
        view.tkraise()
        menu_name = "start" if name == "chat" else name
        for n, b in self.menu_buttons.items():
            on = n == menu_name
            b.configure(fg_color=C["bubble_me"] if on else "transparent", text_color="#ffffff" if on else C["muted"])

    def start_chat(self, mode: str) -> None:
        store = self.services.store
        plan = get_plan(store, date.today())
        self.conversation = Conversation(self.make_llm(), store, plan, mode, load_memory(store),
                                         level=current_level(store))
        self.views["chat"].begin(self.conversation)
        self.show("chat")

    def end_chat(self) -> None:
        conv = self.conversation
        if conv is None:
            return
        self.views["chat"].stop()
        store, session = self.services.store, conv.session
        if not any(m.role == "user" for m in session.messages):
            conv.discard()
            store.delete_session(session.id)
            self.conversation = None
            self.show("start")
            return
        llm = self.make_llm()

        def finish():
            return finalize_session(llm, store, session)

        def done(report):
            self.conversation = None
            self.show("daily")

        def failed(exc):
            self.conversation = None
            self.show("start")

        self.worker.run(finish, done, failed)

    def make_llm(self) -> LLM:
        # 설정(키·모델)이 바뀌면 새로 만들고, 그대로면 연결을 재사용한다
        s = self.services.settings
        key = (id(self.services.llm_factory), s.api_key, s.model)
        if getattr(self, "_llm_key", None) != key:
            self._llm, self._llm_key = self.services.llm_factory(s), key
        return self._llm


_mutex = None


def already_running(name: str = "Local\\HoehwaApp") -> bool:
    """이미 켜져 있으면 그 창을 앞으로 가져오고 True. (눈치백단타이머에서 여러 번 눌러도 창은 하나)"""
    import ctypes

    global _mutex
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, name)
    if ctypes.windll.kernel32.GetLastError() != 183:  # ERROR_ALREADY_EXISTS
        return False
    hwnd = ctypes.windll.user32.FindWindowW(None, APP_NAME)
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        ctypes.windll.user32.SetForegroundWindow(hwnd)
    return True


def run() -> None:
    if already_running():
        return
    services = Services(
        store=Store(DATA_DIR),
        settings=load_settings(),
        llm_factory=lambda s: GeminiLLM(s.api_key, s.model),
    )
    App(services).mainloop()
