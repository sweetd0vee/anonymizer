# -*- coding: utf-8 -*-
"""Настройки программы: %APPDATA%\\Anonymizer\\config.json."""
from __future__ import annotations

import json
import os


def _path() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, "Anonymizer")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "config.json")


def load_settings() -> dict:
    try:
        with open(_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}


def save_settings(settings: dict) -> None:
    try:
        with open(_path(), "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except OSError:
        pass  # настройки не критичны, не роняем программу
