from talk.config import Settings, load_settings, save_settings


def test_missing_file_gives_defaults(tmp_path):
    s = load_settings(tmp_path / "settings.json")
    assert s.daily_goal_min == 20 and s.api_key == "" and s.speed == "normal"
    assert s.model == "gemini-3.5-flash-lite"  # 2.5-flash는 지원 종료 예정


def test_roundtrip(tmp_path):
    p = tmp_path / "settings.json"
    save_settings(Settings(api_key="k", daily_goal_min=30), p)
    assert load_settings(p).api_key == "k" and load_settings(p).daily_goal_min == 30


def test_unknown_and_broken_fields_ignored(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text('{"api_key": "k", "nope": 1}', encoding="utf-8")
    assert load_settings(p).api_key == "k"
    p.write_text("{broken", encoding="utf-8")
    assert load_settings(p) == Settings()
