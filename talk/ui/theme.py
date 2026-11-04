"""색과 글꼴, 자주 쓰는 위젯 모양."""

import customtkinter as ctk

C = {
    "bg": "#1e1f22",
    "side": "#16171a",
    "side_hover": "#202126",
    "panel": "#26282c",
    "bubble_ai": "#2c2d31",
    "bubble_me": "#2b5f9e",
    "accent": "#3b8ed0",
    "accent_hover": "#2f7bbb",
    "fg": "#e6e6e6",
    "muted": "#9a9a9a",
    "line": "#2c2d31",
    "fix_bg": "#26302a",
    "fix_fg": "#cfe8d6",
    "fix_em": "#8fd6a5",
    "fix_chip": "#3a4a3f",
    "help_bg": "#2a2838",
    "help_fg": "#ddd5f7",
    "help_em": "#b9a6f0",
    "help_chip": "#3b3652",
    "trans_bg": "#25272b",
    "trans_chip": "#2c2d31",
    "repeat": "#e8c46a",
    "done": "#2f6b45",
    "track": "#2c2d31",
    "warn": "#ff8787",
}

UI_FONT = "Malgun Gothic"
MONO_FONT = "Consolas"

MODE_LABELS = {"daily": "☕ 일상 대화", "business": "💼 비즈니스", "verb": "🔤 동사 집중", "pattern": "🧩 표현·문형"}


def font(size: int = 13, weight: str = "normal", mono: bool = False) -> ctk.CTkFont:
    return ctk.CTkFont(family=MONO_FONT if mono else UI_FONT, size=size, weight=weight)


def label(parent, text="", size=13, weight="normal", color=None, mono=False, **kw) -> ctk.CTkLabel:
    return ctk.CTkLabel(parent, text=text, font=font(size, weight, mono), text_color=color or C["fg"], **kw)


def button(parent, text, command, primary=False, width=90, height=32) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent, text=text, command=command, width=width, height=height, corner_radius=7,
        fg_color=C["accent"] if primary else C["panel"],
        hover_color=C["accent_hover"] if primary else C["side_hover"],
        text_color="#ffffff" if primary else C["fg"], text_color_disabled=C["muted"],
        font=font(13, "bold" if primary else "normal"),
    )


def card(parent, color=None, **kw) -> ctk.CTkFrame:
    return ctk.CTkFrame(parent, fg_color=color or C["panel"], corner_radius=10, **kw)
