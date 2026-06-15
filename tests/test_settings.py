import email_order_reader.settings as settings_module
from email_order_reader.settings import AppSettings, default_settings_path, load_settings, save_settings


def test_save_and_load_settings_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    settings = AppSettings(email="buyer@example.com", auth_code="secret")

    save_settings(settings, path)
    loaded = load_settings(path)

    assert loaded == settings


def test_load_settings_returns_empty_for_missing_file(tmp_path):
    loaded = load_settings(tmp_path / "missing.json")

    assert loaded == AppSettings()


def test_load_settings_ignores_invalid_json(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{bad json", encoding="utf-8")

    loaded = load_settings(path)

    assert loaded == AppSettings()


def test_default_settings_path_uses_windows_appdata(monkeypatch, tmp_path):
    appdata = tmp_path / "Roaming"
    monkeypatch.setattr(settings_module.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(appdata))

    assert default_settings_path() == appdata / "EmailOrderReader" / "settings.json"


def test_load_settings_migrates_legacy_file_to_windows_appdata(monkeypatch, tmp_path):
    home = tmp_path / "home"
    appdata = tmp_path / "Roaming"
    legacy_path = home / ".email-order-reader" / "settings.json"
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_text('{"email": "saved@example.com", "auth_code": "saved-secret"}', encoding="utf-8")
    monkeypatch.setattr(settings_module.sys, "platform", "win32")
    monkeypatch.setattr(settings_module.Path, "home", lambda: home)
    monkeypatch.setenv("APPDATA", str(appdata))

    loaded = load_settings()

    new_path = appdata / "EmailOrderReader" / "settings.json"
    assert loaded == AppSettings(email="saved@example.com", auth_code="saved-secret")
    assert new_path.exists()
    assert new_path.read_text(encoding="utf-8") == legacy_path.read_text(encoding="utf-8")
