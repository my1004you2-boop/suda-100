from talk.llm import LLMError
from talk.reports import load_daily
from tests.conftest import pump
from tests.test_conversation import turn

OPENING = {"reply": "Hey! Any plans for the weekend?"}
CORR = {"native": "I can't decide between a movie and hiking.", "why_ko": "두 개 중엔 decide between이 자연스러워요.",
        "extend": None}
SUMMARY = {"topic_summary": "Weekend plans.", "new_facts": []}


def start(app):
    app.start_chat("daily")
    view = app.views["chat"]
    assert pump(app, lambda: len(app.conversation.session.messages) == 1 and view.bubble_count == 1)
    return view


def say(app, view, text):
    view.input.delete("1.0", "end")
    view.input.insert("1.0", text)
    view.send()
    n = len(app.conversation.session.messages)
    pump(app, lambda: not view.sending)
    return n


def test_send_shows_bubbles_and_correction_card(make_app):
    app = make_app([OPENING, turn(correction=CORR)])
    view = start(app)
    assert app.current == "chat"
    say(app, view, "i cant choose one of them")
    assert view.bubble_count == 3
    card = view.cards[-1]
    assert card.kind == "fix" and card.expanded
    assert "decide between a movie" in card.text
    assert view.input.get("1.0", "end").strip() == ""


def test_card_folds_and_unfolds(make_app):
    app = make_app([OPENING, turn(correction=dict(CORR, extend="I can't decide. Both sound fun!"))])
    view = start(app)
    say(app, view, "i cant choose one of them")
    card = view.cards[-1]
    assert "이렇게 이어 말할 수도 있어요" in card.text
    card.toggle()
    app.update()
    assert not card.expanded and not card.body.winfo_ismapped()
    assert "원어민 표현 보기" in card.chip.cget("text")
    card.toggle()
    app.update()
    assert card.expanded


def test_help_card_rendered(make_app):
    app = make_app([OPENING, turn(help_ko="'예약 변경'은 change my reservation이에요.", help_expr="change my reservation")])
    view = start(app)
    say(app, view, "예약 변경 영어로 뭐야?")
    assert view.cards[-1].kind == "help" and "change my reservation" in view.cards[-1].text


def test_llm_error_restores_input(make_app):
    app = make_app([OPENING, LLMError("AI가 잠시 바빠요. 잠시 후 다시 시도해 주세요.")])
    view = start(app)
    say(app, view, "hello there")
    assert "잠시 후 다시 시도해 주세요" in view.error_label.cget("text")
    assert view.input.get("1.0", "end").strip() == "hello there"
    assert view.bubble_count == 1 and len(app.conversation.session.messages) == 1


def test_end_chat_writes_daily_and_shows_report(make_app):
    app = make_app([OPENING, turn(correction=CORR), SUMMARY])
    view = start(app)
    say(app, view, "i cant choose one of them")
    session = app.conversation.session
    app.end_chat()
    assert pump(app, lambda: app.current == "daily")
    report = load_daily(app.services.store, session.date)
    assert report["user_messages"] == 1 and report["learned"][0]["native"] == CORR["native"]
    assert app.conversation is None


def test_end_chat_without_user_messages_discards_session(make_app):
    app = make_app([OPENING])
    start(app)
    sid = app.conversation.session.id
    app.end_chat()
    assert pump(app, lambda: app.current == "start")
    assert all(s.id != sid for s in app.services.store.list_sessions())


def test_menu_today_returns_to_active_chat(make_app):
    app = make_app([OPENING])
    start(app)
    app.on_menu("settings")
    app.on_menu("start")
    assert app.current == "chat"


def test_ai_translation_card_starts_folded(make_app):
    app = make_app([dict(OPENING, reply_ko="안녕! 주말에 계획 있어?"), turn(reply_ko="하하, 고르기 어렵네!")])
    view = start(app)
    say(app, view, "i like movies")
    trans = [c for c in view.cards if c.kind == "trans"]
    assert len(trans) == 2
    card = trans[-1]
    app.update()
    assert not card.expanded and not card.body.winfo_ismapped()
    assert "한국어" in card.chip.cget("text") and "하하, 고르기 어렵네!" in card.text
    card.toggle()
    assert card.expanded


def _texts(widget):
    from talk.ui.chat_view import SelectableText

    found = [widget] if isinstance(widget, SelectableText) else []
    for child in widget.winfo_children():
        found += _texts(child)
    return found


def test_bubble_and_card_text_is_selectable_and_read_only(make_app):
    app = make_app([OPENING, turn(correction=CORR)])
    view = start(app)
    say(app, view, "i cant choose one of them")
    app.update()
    texts = {t.get("1.0", "end-1c"): t for t in _texts(view.scroll)}
    assert OPENING["reply"] in texts and "i cant choose one of them" in texts
    assert f"\"{CORR['native']}\"" in texts                     # 교정 카드 글자도 선택 가능
    t = texts[OPENING["reply"]]
    t.tag_add("sel", "1.0", "1.4")
    assert t.get("sel.first", "sel.last") == "Hey!"            # 드래그 선택과 같은 상태

    class Key:
        def __init__(self, keysym, state=0):
            self.keysym, self.state = keysym, state

    assert t._on_key(Key("x")) == "break"                       # 글자 입력은 막고
    assert t._on_key(Key("c", 0x0004)) is None                  # Ctrl+C 복사는 허용


def test_long_text_wraps_without_inner_scroll(make_app):
    long = "This is a fairly long reply that should wrap onto several lines in the bubble. " * 4
    app = make_app([{"reply": long.strip()}])
    view = start(app)
    app.update()
    t = [x for x in _texts(view.scroll) if x.get("1.0", "end-1c") == long.strip()][0]
    t.fit_height()
    assert int(t.cget("height")) == t.display_lines() > 1
