# -*- coding: utf-8 -*-
"""Пайплайн обезличивания: детекция → теги → замена → восстановление.

Порядок работы с одним документом
---------------------------------
1. `readers.load` / `load_from_bytes` даёт плоский текст и, для DOCX,
   карту абзацев (`LoadedDoc.fragments`).
2. `Analyzer.detect` собирает сущности:
     regex-реквизиты + regex-организации + Natasha NER
     → склейка ключей ФИО → разрешение пересечений.
3. `apply_tags` / `apply_package_tags` выдаёт теги `[ФИО1]`, `[ИНН1]`, …
   Одинаковый `(type, norm_key)` — один тег на весь пакет файлов.
4. `anonymize_text` или `anonymize_document` подставляет теги.
   DOCX правится по runs, чтобы сохранить жирный/курсив.
   PDF/TXT всегда идут через плоский текст.
5. `TagRegistry.to_mapping` пишет JSON-таблицу соответствий.
6. `deanonymize_text` возвращает исходные значения по таблице
   (терпимо к пробелам внутри тега, которые иногда вставляет LLM).

Теги получают и выключенные сущности — чтобы включение категории обратно
не сбивало нумерацию. В JSON попадают только реально использованные теги.
"""
from __future__ import annotations

from .detectors import detect_orgs_regex, detect_structured
from .entities import OVERLAP_PRIORITY, Entity, TagRegistry
from .ner import NerEngine, merge_person_keys
from .replace import anonymize_document, anonymize_text, deanonymize_text

__all__ = [
    "Analyzer",
    "anonymize_document",
    "anonymize_text",
    "apply_package_tags",
    "apply_tags",
    "deanonymize_text",
    "find_manual_occurrences",
    "resolve_overlaps",
]


class Analyzer:
    """Оркестратор детекции. Модели Natasha грузятся при первом вызове."""

    def __init__(self, ner: NerEngine | None = None) -> None:
        self.ner = ner or NerEngine()

    def detect(self, text: str) -> list[Entity]:
        entities = detect_structured(text)
        entities += detect_orgs_regex(text)
        entities += self.ner.detect(text)
        merge_person_keys(entities)
        return resolve_overlaps(entities)


def resolve_overlaps(entities: list[Entity]) -> list[Entity]:
    """При пересечении спанов выигрывает высокий приоритет, затем длина."""
    ordered = sorted(
        entities,
        key=lambda e: (-OVERLAP_PRIORITY.get(e.type, 0), -(e.stop - e.start), e.start),
    )
    chosen: list[Entity] = []
    for entity in ordered:
        if not any(entity.overlaps(current) for current in chosen):
            chosen.append(entity)
    chosen.sort(key=lambda e: e.start)
    return chosen


def find_manual_occurrences(text: str, fragment: str) -> list[tuple[int, int]]:
    """Все непересекающиеся вхождения строки (для ручного добавления сущности)."""
    out: list[tuple[int, int]] = []
    start, length = 0, len(fragment)
    while True:
        index = text.find(fragment, start)
        if index < 0:
            break
        out.append((index, index + length))
        start = index + length
    return out


def apply_tags(entities: list[Entity], registry: TagRegistry) -> None:
    """Присвоить теги всем сущностям в порядке появления в тексте."""
    for entity in sorted(entities, key=lambda item: item.start):
        registry.assign(entity)


def apply_package_tags(entity_lists: list[list[Entity]], registry: TagRegistry) -> None:
    """Склейка ключей ФИО по всему пакету файлов, затем выдача тегов."""
    merge_person_keys([entity for entities in entity_lists for entity in entities])
    for entities in entity_lists:
        apply_tags(entities, registry)
