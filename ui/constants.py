# -*- coding: utf-8 -*-
"""Константы веб-интерфейса."""
from __future__ import annotations

from anon.entities import SETTING_TYPES

APP_TITLE = "Анонимизатор документов"

COLORS = {
    "FIO": "#ffd6d6", "ORG": "#d6e4ff", "ADDR": "#d9f2d9", "DATE": "#fde6c8",
    "INN": "#fff2c2", "OGRN": "#fff2c2", "KPP": "#fff2c2", "BIK": "#fff2c2",
    "SNILS": "#ffe0f0", "PASSPORT": "#ffcfa8", "ACCOUNT": "#e2d6ff",
    "PHONE": "#c9f0f0", "EMAIL": "#c9f0f0", "SITE": "#c9e8ff", "OTHER": "#e0e0e0",
}

MIME = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".json": "application/json",
    ".zip": "application/zip",
}

AVAILABLE_TYPES = {code for code, _ in SETTING_TYPES}
DOWNLOAD_FORMATS = ["PDF", "DOCX", "TXT", "CSV"]
FORMAT_EXT = {"PDF": ".pdf", "DOCX": ".docx", "TXT": ".txt", "CSV": ".csv"}
EXT_FORMAT = {".pdf": "PDF", ".docx": "DOCX", ".txt": "TXT", ".csv": "CSV"}
