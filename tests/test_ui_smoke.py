from talk.config import load_settings

VIEWS = ["start", "chat", "daily", "weekly", "history", "settings"]


def test_app_builds_and_switches_views(make_app):
    app = make_app()
    for name in VIEWS:
        app.show(name)
        app.update()
        assert app.current == name
    assert app.title() == "수다백단"


def test_settings_view_saves(make_app, tmp_path):
    app = make_app()
    app.show("settings")
    view = app.views["settings"]
    view.key_entry.delete(0, "end")
    view.key_entry.insert(0, "new-key")
    view.goal_entry.delete(0, "end")
    view.goal_entry.insert(0, "30")
    view.speed_var.set("원어민 속도")
    view.save()
    saved = load_settings(tmp_path / "settings.json")
    assert saved.api_key == "new-key" and saved.daily_goal_min == 30 and saved.speed == "native"
    assert app.services.settings.api_key == "new-key"


def test_settings_bad_goal_keeps_old_value(make_app, tmp_path):
    app = make_app()
    app.show("settings")
    view = app.views["settings"]
    view.goal_entry.delete(0, "end")
    view.goal_entry.insert(0, "abc")
    view.save()
    assert load_settings(tmp_path / "settings.json").daily_goal_min == 20
