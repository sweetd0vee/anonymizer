# -*- coding: utf-8 -*-
"""Локальный анонимизатор юридических документов.

Публичный API ядра: детекция (`Analyzer`), замена тегов, чтение/запись файлов
и реестр соответствий (`TagRegistry`). Веб-интерфейс — `app.py`.
"""
from .engine import (
    Analyzer,
    anonymize_text,
    apply_package_tags,
    apply_tags,
    deanonymize_text,
)
from .entities import Entity, TagRegistry
from .readers import load, load_from_bytes
from .writers import anonymized_bytes, save_anonymized

__version__ = "1.0.0"
__all__ = [
    "Analyzer",
    "Entity",
    "TagRegistry",
    "anonymize_text",
    "anonymized_bytes",
    "apply_package_tags",
    "apply_tags",
    "deanonymize_text",
    "load",
    "load_from_bytes",
    "save_anonymized",
]
