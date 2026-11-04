"""대화 화면: 말풍선, 접을 수 있는 교정·도움말 카드, 입력창과 마이크, 오늘 목표 막대."""

import traceback

import customtkinter as ctk

from talk.llm import LLMError
from talk.models import Message
from talk.reports import goal_progress
from talk.ui.theme import C, MODE_LABELS, button, font, label

BUBBLE_WRAP = 520
ERROR_MS = 5000

CARD_STYLE = {
    "fix": {"bg": "fix_bg", "fg": "fix_fg", "em": "fix_em", "chip": "fix_chip", "chip_text": "💬 원어민 표현 보기 ▼"},
    "help": {"bg": "help_bg", "fg": "help_fg", "em": "help_em", "chip": "help_chip", "chip_text": "💡 도움말 보기 ▼"},
    "trans": {"bg": "trans_bg", "fg": "fg", "em": "muted", "chip": "trans_chip", "chip_text": "🌏 한국어 번역 보기 ▼"},
}


class FoldCard(ctk.CTkFrame):
    """처음엔 펼쳐져 있고, '접기'를 누르면 작은 버튼으로 줄어드는 카드."""

    def __init__(self, master, kind: str, lines: list[tuple[str, bool]], expanded: bool = True, side: str = "e"):
        super().__init__(master, fg_color="transparent")
        st = CARD_STYLE[kind]
        self.kind = kind
        self.side = side
        self.text = "\n".join(t for t, _ in lines)
        self.body = ctk.CTkFrame(self, fg_color=C[st["bg"]], corner_radius=8, border_width=0)
        top = ctk.CTkFrame(self.body, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(6, 0))
        fold = label(top, "접기 ▲", 11, color=C[st["em"]], cursor="hand2")
        fold.pack(side="right")
        fold.bind("<Button-1>", lambda e: self.toggle())
        for text, em in lines:
            label(self.body, text, 12, "bold" if em else "normal", color=C[st["em"]] if em else C[st["fg"]],
                  wraplength=BUBBLE_WRAP - 40, justify="left").pack(anchor="w", padx=12, pady=(0, 2))
        ctk.CTkFrame(self.body, fg_color="transparent", height=6).pack()
        self.chip = ctk.CTkButton(self, text=st["chip_text"], command=self.toggle, height=24, corner_radius=12,
                                  font=font(11), fg_color=C[st["chip"]], hover_color=C[st["bg"]],
                                  text_color=C[st["em"]], width=10)
        self.expanded = not expanded
        self.toggle()

    def toggle(self) -> None:
        self.expanded = not self.expanded
        if self.expanded:
            self.chip.pack_forget()
            self.body.pack(anchor=self.side)
        else:
            self.body.pack_forget()
            self.chip.pack(anchor=self.side)


def message_cards(msg: Message) -> list[tuple[str, list[tuple[str, bool]]]]:
    cards = []
    if msg.correction:
        lines = [("💬 원어민은 이렇게도 말해요:", False), (f"\"{msg.correction.native}\"", True),
                 (msg.correction.why_ko, False)]
        if msg.correction.extend:
            lines += [("➕ 이렇게 이어 말할 수도 있어요:", False), (f"\"{msg.correction.extend}\"", True)]
        cards.append(("fix", lines))
    if msg.help_ko:
        cards.append(("help", [("💡 도움말", False), (msg.help_ko, False)]))
    if msg.translation_ko:
        cards.append(("trans", [("🌏 한국어 번역", False), (msg.translation_ko, False)]))
    return cards


def render_message(parent, msg: Message, on_speak) -> tuple[ctk.CTkFrame, list[FoldCard]]:
    """말풍선 하나(와 그 아래 카드들)를 그린다. 기록 화면에서도 같이 쓴다."""
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", padx=12, pady=4)
    mine = msg.role == "user"
    bubble = ctk.CTkFrame(row, fg_color=C["bubble_me"] if mine else C["bubble_ai"], corner_radius=10)
    bubble.pack(anchor="e" if mine else "w")
    text = ("🎤 " if msg.via_voice else "") + msg.text
    label(bubble, text, 13, wraplength=BUBBLE_WRAP, justify="left").pack(side="left", padx=11, pady=8)
    if not mine and on_speak:
        ctk.CTkButton(bubble, text="🔊", width=28, height=24, fg_color="transparent", hover_color=C["side_hover"],
                      text_color=C["accent"], font=font(12), command=lambda: on_speak(msg.text)).pack(
            side="left", padx=(0, 6))
    cards = []
    side = "e" if mine else "w"
    for kind, lines in message_cards(msg):
        c = FoldCard(row, kind, lines, expanded=kind != "trans", side=side)  # 번역은 접힌 채로 시작
        c.pack(anchor=side, pady=(4, 0))
        cards.append(c)
    return row, cards


class ChatView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=C["bg"], corner_radius=0)
        self.app = app
        self.conversation = None
        self.sending = False
        self.recording = False
        self.bubble_count = 0
        self.cards: list[FoldCard] = []
        self._pending: list = []
        self._error_job = None
        self._tick_job = None
        self._status_label = None

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(14, 6))
        self.mode_chip = self._chip(top)
        self.topic_chip = self._chip(top)
        self.end_button = button(top, "대화 끝내기", self.end, width=96)
        self.end_button.pack(side="right")
        self.time_label = label(top, "", 12, color=C["muted"], mono=True)
        self.time_label.pack(side="right", padx=10)
        self.bar = ctk.CTkProgressBar(top, height=8, progress_color=C["accent"], fg_color=C["track"])
        self.bar.pack(side="left", fill="x", expand=True, padx=10)
        self.error_label = label(self, "", 12, color=C["warn"])
        self.error_label.pack(fill="x", padx=16)

        self.scroll = ctk.CTkScrollableFrame(self, fg_color=C["bg"], corner_radius=0)
        self.scroll.pack(fill="both", expand=True, padx=4)

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=16, pady=(6, 14))
        self.input = ctk.CTkTextbox(bottom, height=56, font=font(13), fg_color=C["panel"], border_width=0,
                                    corner_radius=8, wrap="word")
        self.input.pack(side="left", fill="x", expand=True)
        self.input.bind("<Return>", self._on_enter)
        self.send_button = button(bottom, "보내기", self.send, primary=True, width=72, height=56)
        self.send_button.pack(side="left", padx=(8, 0))
        self.mic_button = button(bottom, "🎤", None, width=56, height=56)
        if app.services.speech_enabled and app.has_mic:
            self.mic_button.pack(side="left", padx=(8, 0))
            self.mic_button.bind("<ButtonPress-1>", lambda e: self.mic_down())
            self.mic_button.bind("<ButtonRelease-1>", lambda e: self.mic_up())

    def _chip(self, parent) -> ctk.CTkLabel:
        c = ctk.CTkLabel(parent, text="", font=font(12), fg_color=C["panel"], corner_radius=12, height=26,
                         text_color=C["fg"])
        c.pack(side="left", padx=(0, 6), ipadx=8)
        return c

    # ----- 대화 시작 · 끝 -----
    def begin(self, conversation) -> None:
        self.conversation = conversation
        for w in self.scroll.winfo_children():
            w.destroy()
        self.bubble_count, self.cards, self._pending = 0, [], []
        self.mode_chip.configure(text=MODE_LABELS[conversation.mode])
        self.topic_chip.configure(text=conversation.session.topic)
        self.input.delete("1.0", "end")
        self.end_button.configure(state="normal")
        self._show_typing()
        self._open()
        self._tick()

    def _open(self) -> None:
        conv = self.conversation
        conv.llm = self.app.make_llm()
        self.app.worker.run(conv.opening, lambda text: self._opened(conv, text),
                            lambda exc: self._open_failed(conv, exc))

    def _opened(self, conv, text) -> None:
        if conv is not self.conversation:
            return  # 첫 마디가 오기 전에 대화를 끝냄
        self._clear_pending()
        self._add(conv.session.messages[-1])
        self._maybe_auto_read(text)

    def _open_failed(self, conv, exc) -> None:
        if conv is not self.conversation:
            return
        self._clear_pending()
        row = ctk.CTkFrame(self.scroll, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=8)
        self._status_label = label(row, getattr(exc, "message_ko", "AI에 연결하지 못했어요."), 12, color=C["warn"])
        self._status_label.pack(side="left")
        button(row, "다시 시도", self.retry_open, width=80).pack(side="left", padx=8)
        self._pending.append(row)

    def retry_open(self) -> None:
        if self.conversation is None:
            return
        self._clear_pending()
        self._status_label = None
        self._show_typing()
        self._open()

    def status_text(self) -> str:
        try:
            return self._status_label.cget("text") if self._status_label else ""
        except Exception:
            return ""

    def stop(self) -> None:
        if self._tick_job:
            self.after_cancel(self._tick_job)
            self._tick_job = None
        self.conversation = None

    def end(self) -> None:
        if self.conversation is None or self.sending:
            return
        self.end_button.configure(state="disabled")
        self.send_button.configure(state="disabled")
        self.error_label.configure(text="오늘 대화를 정리하고 있어요…", text_color=C["muted"])
        self.app.end_chat()

    # ----- 말풍선 -----
    def _add(self, msg: Message) -> None:
        _, cards = render_message(self.scroll, msg, self.speak if self.app.services.speech_enabled else None)
        self.bubble_count += 1
        self.cards += cards
        self._scroll_bottom()

    def _show_typing(self) -> None:
        row = ctk.CTkFrame(self.scroll, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=4)
        bubble = ctk.CTkFrame(row, fg_color=C["bubble_ai"], corner_radius=10)
        bubble.pack(anchor="w")
        label(bubble, "…", 13, color=C["muted"]).pack(padx=14, pady=6)
        self._pending.append(row)
        self._scroll_bottom()

    def _clear_pending(self) -> None:
        for w in self._pending:
            w.destroy()
        self._pending = []

    def _scroll_bottom(self) -> None:
        self.after(30, lambda: self.scroll._parent_canvas.yview_moveto(1.0))

    # ----- 보내기 -----
    def _on_enter(self, event):
        if event.state & 0x0001:  # Shift+Enter는 줄바꿈
            return None
        self.send()
        return "break"

    def send(self, text: str | None = None, via_voice: bool = False) -> None:
        if self.sending or self.conversation is None or not self.conversation.session.messages:
            return
        if text is None:
            text = self.input.get("1.0", "end").strip()
            self.input.delete("1.0", "end")
        if not text:
            return
        self.sending = True
        self.send_button.configure(state="disabled")
        temp = Message("user", text, "", via_voice=via_voice)
        row, _ = render_message(self.scroll, temp, None)
        self._pending.append(row)
        self._show_typing()
        conv = self.conversation
        conv.llm = self.app.make_llm()
        self.app.worker.run(lambda: conv.send(text, via_voice),
                            lambda r: self._sent(conv), lambda e: self._send_failed(conv, e, text))

    def _sent(self, conv) -> None:
        self._done_sending()
        if conv is not self.conversation:
            return
        self._clear_pending()
        user_msg, ai_msg = conv.session.messages[-2:]
        self._add(user_msg)
        self._add(ai_msg)
        self._maybe_auto_read(ai_msg.text)

    def _send_failed(self, conv, exc, text) -> None:
        self._done_sending()
        if conv is not self.conversation:
            return
        self._clear_pending()
        # 보낸 문장(음성이면 알아들은 문장)을 입력창에 돌려준다. 그새 쓴 글은 지우지 않는다
        typed = self.input.get("1.0", "end").strip()
        self.input.delete("1.0", "end")
        self.input.insert("1.0", f"{text} {typed}".strip())
        msg = exc.message_ko if isinstance(exc, LLMError) else "잠시 후 다시 시도해 주세요."
        self.show_error(msg)

    def _done_sending(self) -> None:
        self.sending = False
        self.send_button.configure(state="normal")

    def show_error(self, text: str) -> None:
        self.error_label.configure(text=text, text_color=C["warn"])
        if self._error_job:
            self.after_cancel(self._error_job)
        self._error_job = self.after(ERROR_MS, lambda: self.error_label.configure(text=""))

    # ----- 음성 -----
    def speak(self, text: str) -> None:
        from talk.speech import speak

        s = self.app.services.settings
        self.app.worker.run(lambda: speak(text, s.voice, s.speed), None,
                            lambda e: self.show_error("음성을 재생하지 못했어요. 인터넷 연결을 확인해 주세요."))

    def _maybe_auto_read(self, text: str) -> None:
        if self.app.services.speech_enabled and self.app.services.settings.auto_read:
            self.speak(text)

    def mic_down(self) -> None:
        if self.sending or not self.app.transcriber.ready:
            return
        try:
            self.app.recorder.device = self.app.services.settings.mic_device
            self.app.recorder.start()
            self.recording = True
            self.mic_button.configure(fg_color=C["warn"], text="●")
        except Exception:
            self.show_error("마이크를 열지 못했어요. 설정에서 마이크를 확인해 주세요.")

    def mic_up(self) -> None:
        if not self.recording:
            return
        self.recording = False
        self.mic_button.configure(fg_color=C["panel"], text="🎤")
        audio = self.app.recorder.stop()
        if audio.size == 0:
            return
        self.mic_button.configure(state="disabled", text="…")

        def heard(text):
            self.mic_button.configure(state="normal", text="🎤")
            if text:
                self.send(text, via_voice=True)
            else:
                self.show_error("잘 못 알아들었어요. 다시 말해 주세요.")

        def failed(exc):
            self.mic_button.configure(state="normal", text="🎤")
            self.show_error("음성을 글자로 바꾸지 못했어요.")

        self.app.worker.run(lambda: self.app.transcriber.transcribe(audio), heard, failed)

    # ----- 시간 -----
    def _tick(self) -> None:
        if self.conversation is None:
            return
        try:
            self._update_time()
        except Exception:
            traceback.print_exc()  # 한 번 실패해도 타이머는 계속 돈다
        self._tick_job = self.after(1000, self._tick)

    def _update_time(self) -> None:
        conv = self.conversation
        try:
            iconic = self.app.state() == "iconic"
        except Exception:
            iconic = False
        if not iconic and conv.session.messages:
            conv.add_seconds(1)
        done, goal = goal_progress(self.app.services.store, conv.session.date, self.app.services.settings,
                                   live_seconds=conv.session.seconds)
        self.bar.set(min(1.0, done / goal) if goal else 1.0)
        if done >= goal:
            self.bar.configure(progress_color=C["fix_em"])
            self.time_label.configure(text=f"오늘 목표 완료 🎉  {done} / {goal}분")
        else:
            self.bar.configure(progress_color=C["accent"])
            self.time_label.configure(text=f"{done} / {goal}분")
        if self.app.services.speech_enabled:
            ready = self.app.transcriber.ready
            if not self.recording and not self.sending and self.mic_button.cget("text") in ("🎤", "음성 준비 중…"):
                self.mic_button.configure(text="🎤" if ready else "음성 준비 중…", state="normal" if ready else "disabled",
                                          width=56 if ready else 110)

    def refresh(self) -> None:
        pass
