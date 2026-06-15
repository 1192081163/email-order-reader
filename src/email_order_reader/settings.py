from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppSettings:
    email: str = ""
    auth_code: str = ""


APP_NAME = "EmailOrderReader"


def legacy_settings_path() -> Path:
    return Path.home() / ".email-order-reader" / "settings.json"


def default_settings_path() -> Path:
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        base_path = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base_path / APP_NAME / "settings.json"

    return legacy_settings_path()


def load_settings(path: Path | None = None) -> AppSettings:
    settings_path = path or default_settings_path()
    if path is None:
        migrate_legacy_settings(settings_path)

    try:
        raw = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return AppSettings()

    if not isinstance(raw, dict):
        return AppSettings()

    return AppSettings(
        email=str(raw.get("email") or "").strip(),
        auth_code=str(raw.get("auth_code") or ""),
    )


def migrate_legacy_settings(settings_path: Path) -> None:
    legacy_path = legacy_settings_path()
    if settings_path == legacy_path or settings_path.exists() or not legacy_path.exists():
        return

    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(legacy_path.read_text(encoding="utf-8"), encoding="utf-8")
    except OSError:
        return


def save_settings(settings: AppSettings, path: Path | None = None) -> None:
    settings_path = path or default_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(
            {
                "email": settings.email,
                "auth_code": settings.auth_code,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
