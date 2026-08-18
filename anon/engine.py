# -*- coding: utf-8 -*-
"""Ядро: поиск сущностей, замена на теги, обратное восстановление."""
from __future__ import annotations

import re

from .detectors import detect_orgs_regex, detect_structured
from .entities import Entity, TagRegistry
from .ner import NerEngine, merge_person_keys
from .readers import LoadedDoc

# приоритет при пересечении (больше — важнее): регулярки с чек-суммами точнее NER
PRIORITY = {
    "SNILS": 10, "ACCOUNT": 10, "OGRN": 10, "INN": 10, "PASSPORT": 9,
    "BIK": 9, "KPP": 9, "PHONE": 8, "EMAIL": 8, "DATE": 8, "ADDR": 7,
    "ORG": 5, "FIO": 5, "OTHER": 4,
}


class Analyzer:
    def __init__(self):
        self.ner = NerEngine()

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
        key=lambda e: (-PRIORITY.get(e.type, 0), -(e.stop - e.start), e.start),
    )
    chosen: list[Entity] = []
    for e in ordered:
        if not any(e.overlaps(c) for c in chosen):
            chosen.append(e)
    chosen.sort(key=lambda e: e.start)
    return chosen


def find_manual_occurrences(text: str, fragment: str) -> list[tuple[int, int]]:
    """Все вхождения строки (для ручного добавления сущности)."""
    out = []
    start, n = 0, len(fragment)
    while True:
        i = text.find(fragment, start)
        if i < 0:
            break
        out.append((i, i + n))
        start = i + n
    return out


def apply_tags(entities: list[Entity], registry: TagRegistry) -> None:
    """Присвоить теги всем сущностям (в порядке появления в тексте).

    Теги получают и выключенные сущности — чтобы при включении типа обратно
    не пришлось пересчитывать нумерацию. В файл соответствий попадают
    только реально использованные теги.
    """
    for e in sorted(entities, key=lambda x: x.start):
        registry.assign(e)


def apply_package_tags(entity_lists: list[list[Entity]], registry: TagRegistry) -> None:
    """Склейка ключей ФИО по всему пакету файлов, затем выдача тегов."""
    merge_person_keys([e for ents in entity_lists for e in ents])
    for ents in entity_lists:
        apply_tags(ents, registry)


def _active(entities: list[Entity]) -> list[Entity]:
    return [e for e in entities if e.enabled and e.tag]


def _replace_plain(text: str, replacements: list[tuple[int, int, str]]) -> str:
    for start, stop, tag in sorted(replacements, key=lambda r: r[0], reverse=True):
        text = text[:start] + tag + text[stop:]
    return text


def anonymize_text(text: str, entities: list[Entity]) -> str:
    """Замена включённых сущностей на теги. Теги должны быть уже присвоены."""
    return _replace_plain(text, [(e.start, e.stop, e.tag) for e in _active(entities)])


def _distribute_replacements(
    texts: list[str], offsets: list[int], entities: list[Entity],
) -> dict[int, list[tuple[int, int, str]]]:
    """Раскладывает глобальные спаны по фрагментам (в т.ч. сущность на стыке)."""
    per_unit: dict[int, list[tuple[int, int, str]]] = {}
    for e in sorted(_active(entities), key=lambda x: x.start):
        placed_tag = False
        for idx, text in enumerate(texts):
            p_start = offsets[idx]
            p_end = p_start + len(text)
            if e.stop <= p_start or e.start >= p_end:
                continue
            loc_start = max(0, e.start - p_start)
            loc_stop = min(len(text), e.stop - p_start)
            tag = e.tag if not placed_tag else ""
            placed_tag = True
            per_unit.setdefault(idx, []).append((loc_start, loc_stop, tag))
    return per_unit


def anonymize_document(loaded: LoadedDoc, entities: list[Entity]):
    """Заменяет сущности в структурированном документе. Возвращает объект для .save()."""
    fragments = loaded.fragments
    if fragments is None or loaded.source is None:
        raise ValueError(f"Нет структурированных данных для {loaded.kind}")
    if loaded.kind == "docx":
        texts = [p.text for p in fragments.units]
        per_unit = _distribute_replacements(texts, fragments.offsets, entities)
        for idx, repls in per_unit.items():
            _replace_in_paragraph(fragments.units[idx], repls)
        return loaded.source
    if loaded.kind in ("xlsx", "pptx"):
        per_unit = _distribute_replacements(fragments.texts, fragments.offsets, entities)
        for idx, repls in per_unit.items():
            _apply_unit(fragments.units[idx], fragments.texts[idx], repls)
        return loaded.source
    raise ValueError(f"Нет структурированной замены для {loaded.kind}")


def _apply_unit(unit, original: str, replacements: list[tuple[int, int, str]]) -> None:
    if callable(unit):
        unit(_replace_plain(original, replacements))
        return
    kind, obj = unit
    if kind == "para" and getattr(obj, "runs", ()):
        _replace_in_paragraph(obj, replacements)
    elif kind == "para":
        obj.text = _replace_plain(original, replacements)
    else:
        obj(_replace_plain(original, replacements))


def _replace_in_paragraph(paragraph, replacements: list[tuple[int, int, str]]):
    """Замена по локальным координатам с сохранением форматирования runs."""
    for start, stop, tag in sorted(replacements, key=lambda r: r[0], reverse=True):
        pos = 0
        spans = []
        for r in paragraph.runs:
            spans.append((r, pos, pos + len(r.text)))
            pos += len(r.text)
        affected = [(r, a, b) for r, a, b in spans if a < stop and start < b]
        if not affected:
            continue
        first_run, fa, _ = affected[0]
        last_run, la, _ = affected[-1]
        head = first_run.text[: start - fa]
        tail = last_run.text[stop - la:] if stop - la <= len(last_run.text) else ""
        if first_run is last_run:
            first_run.text = head + tag + tail
        else:
            first_run.text = head + tag
            for r, _, _ in affected[1:-1]:
                r.text = ""
            last_run.text = tail


def deanonymize_text(text: str, mapping: dict) -> tuple[str, list[str]]:
    """Замена тегов на исходные значения. Возвращает (текст, не найденные теги)."""
    items: list[tuple[str, str, str]] = []
    for tag, rec in mapping.get("tags", {}).items():
        # терпимо к искажениям LLM: [ ФИО1 ], [ФИО 1], **[ФИО1]**
        m = re.match(r"([А-ЯЁA-Z]+)(\d+)", tag.strip("[]"))
        if not m:
            continue
        items.append((m.group(1), m.group(2), rec["canonical"]))
    # длинные номера раньше коротких: [ФИО10] не должен стать заменой [ФИО1]
    items.sort(key=lambda x: (-len(x[1]), x[0]))
    out = text
    for label, num, canonical in items:
        rx = re.compile(r"\[\s*" + re.escape(label) + r"\s*" + re.escape(num) + r"\s*\]")
        out = rx.sub(lambda _m, value=canonical: value, out)
    leftover = sorted(set(re.findall(r"\[[А-ЯЁA-Z]+\s*\d+\]", out)))
    return out, leftover
