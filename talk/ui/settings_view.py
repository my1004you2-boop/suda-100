"""설정 화면."""

from dataclasses import replace

import customtkinter as ctk

from talk.config import save_settings
from talk.ui.theme import C, button, card, font, label

VOICES = {
    "Ava (미국, 여)": "en-US-AvaMultilingualNeural",
    "Andrew (미국, 남)": "en-US-AndrewMultilingualNeural",
    "Emma (미국, 여)": "en-US-EmmaMultilingualNeural",
    "Brian (미국, 남)": "en-US-BrianMultilingualNeural",
    "Sonia (영국, 여)": "en-GB-SoniaNeural",
    "Ryan (영국, 남)": "en-GB-RyanNeural",
}
SPEEDS = {"천천히": "slow", "보통": "normal", "원어민 속도": "native"}
DEFAULT_MIC = "기본 마이크"


def _key_for(mapping: dict, value, default):
    return next((k for k, v in mapping.items() if v == value), default)


class SettingsView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=C["bg"], corner_radius=0)
        self.app = app
        label(self, "설정", 18, "bold").pack(anchor="w", padx=24, pady=(20, 10))
        box = card(self)
        box.pack(fill="x", padx=24)
        box.grid_columnconfigure(1, weight=1)

        def row(r, text):
            label(box, text, color=C["muted"]).grid(row=r, column=0, sticky="w", padx=16, pady=8)

        def entry(r, **kw):
            e = ctk.CTkEntry(box, font=font(13), fg_color=C["bg"], border_color=C["line"], **kw)
            e.grid(row=r, column=1, sticky="ew", padx=16, pady=8)
            return e

        row(0, "Gemini API 키")
        self.key_entry = entry(0, show="•")
        row(1, "모델 이름")
        self.model_entry = entry(1)
        row(2, "하루 목표 (분)")
        self.goal_entry = entry(2, width=80)
        self.goal_entry.grid(sticky="w")

        row(3, "영어 음성")
        self.voice_var = ctk.StringVar()
        ctk.CTkOptionMenu(box, values=list(VOICES), variable=self.voice_var, font=font(13),
                          fg_color=C["bubble_ai"], button_color=C["bubble_ai"]).grid(
            row=3, column=1, sticky="w", padx=16, pady=8)
        row(4, "읽기 속도")
        self.speed_var = ctk.StringVar()
        ctk.CTkSegmentedButton(box, values=list(SPEEDS), variable=self.speed_var, font=font(13)).grid(
            row=4, column=1, sticky="w", padx=16, pady=8)
        row(5, "자동 읽기")
        self.auto_var = ctk.BooleanVar()
        ctk.CTkSwitch(box, text="AI 답장이 오면 바로 읽어주기", variable=self.auto_var, font=font(13)).grid(
            row=5, column=1, sticky="w", padx=16, pady=8)
        row(6, "마이크")
        self.mics = self._list_mics()
        self.mic_var = ctk.StringVar()
        ctk.CTkOptionMenu(box, values=[DEFAULT_MIC] + list(self.mics), variable=self.mic_var, font=font(13),
                          fg_color=C["bubble_ai"], button_color=C["bubble_ai"], width=320).grid(
            row=6, column=1, sticky="w", padx=16, pady=8)

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=24, pady=12)
        button(bottom, "저장", self.save, primary=True).pack(side="left")
        self.status = label(bottom, "", color=C["fix_em"])
        self.status.pack(side="left", padx=12)
        label(self, "무료 Gemini는 대화를 서비스 개선에 쓸 수 있어요. 실제 회사 정보는 넣지 마세요.", 12,
              color=C["muted"]).pack(anchor="w", padx=24)

    def _list_mics(self) -> dict[str, int]:
        if not self.app.services.speech_enabled:
            return {}
        from talk.speech import list_input_devices

        return {f"{i}: {name}": i for i, name in list_input_devices()}

    def refresh(self) -> None:
        s = self.app.services.settings
        for e, v in ((self.key_entry, s.api_key), (self.model_entry, s.model), (self.goal_entry, s.daily_goal_min)):
            e.delete(0, "end")
            e.insert(0, str(v))
        self.voice_var.set(_key_for(VOICES, s.voice, next(iter(VOICES))))
        self.speed_var.set(_key_for(SPEEDS, s.speed, "보통"))
        self.auto_var.set(s.auto_read)
        self.mic_var.set(_key_for(self.mics, s.mic_device, DEFAULT_MIC))
        self.status.configure(text="")

    def save(self) -> None:
        s = self.app.services.settings
        try:
            goal = max(1, int(self.goal_entry.get().strip()))
        except ValueError:
            goal = s.daily_goal_min
        new = replace(
            s,
            api_key=self.key_entry.get().strip(),
            model=self.model_entry.get().strip() or s.model,
            daily_goal_min=goal,
            voice=VOICES.get(self.voice_var.get(), s.voice),
            speed=SPEEDS.get(self.speed_var.get(), s.speed),
            auto_read=bool(self.auto_var.get()),
            mic_device=self.mics.get(self.mic_var.get()),
        )
        self.app.services.settings = new
        save_settings(new, self.app.services.settings_path)
        self.goal_entry.delete(0, "end")
        self.goal_entry.insert(0, str(goal))
        self.status.configure(text="저장했어요", text_color=C["fix_em"])
