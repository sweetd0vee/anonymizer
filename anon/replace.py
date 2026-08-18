# -*- coding: utf-8 -*-
"""Подстановка тегов в текст/DOCX и обратное восстановление."""
from __future__ import annotations

import re

from .entities import Entity
from .readers import LoadedDoc


def _active(entities: list[Entity]) -> list[Entity]:
    return [entity for entity in entities if entity.enabled and entity.tag]


def _replace_plain(text: str, replacements: list[tuple[int, int, str]]) -> str:
    for start, stop, tag in sorted(replacements, key=lambda item: item[0], reverse=True):
        text = text[:start] + tag + text[stop:]
    return text


def anonymize_text(text: str, entities: list[Entity]) -> str:
    """Замена включённых сущностей на теги. Теги должны быть уже присвоены."""
    return _replace_plain(
        text, [(entity.start, entity.stop, entity.tag) for entity in _active(entities)],
    )


def _distribute_replacements(
    texts: list[str], offsets: list[int], entities: list[Entity],
) -> dict[int, list[tuple[int, int, str]]]:
    """Раскладывает глобальные спаны по фрагментам (в т.ч. сущность на стыке абзацев).

    Тег ставится только в первый затронутый фрагмент, хвост в следующих
    обнуляется — иначе `[АДРЕС1]` продублировался бы на каждой строке.
    """
    per_unit: dict[int, list[tuple[int, int, str]]] = {}
    for entity in sorted(_active(entities), key=lambda item: item.start):
        placed_tag = False
        for idx, fragment in enumerate(texts):
            part_start = offsets[idx]
            part_end = part_start + len(fragment)
            if entity.stop <= part_start or entity.start >= part_end:
                continue
            loc_start = max(0, entity.start - part_start)
            loc_stop = min(len(fragment), entity.stop - part_start)
            tag = entity.tag if not placed_tag else ""
            placed_tag = True
            per_unit.setdefault(idx, []).append((loc_start, loc_stop, tag))
    return per_unit


def anonymize_document(loaded: LoadedDoc, entities: list[Entity]):
    """Заменяет сущности в структурированном DOCX. Возвращает объект для `.save()`."""
    fragments = loaded.fragments
    if fragments is None or loaded.source is None:
        raise ValueError(f"Нет структурированных данных для {loaded.kind}")
    if loaded.kind == "docx":
        texts = [para.text for para in fragments.units]
        per_unit = _distribute_replacements(texts, fragments.offsets, entities)
        for idx, replacements in per_unit.items():
            _replace_in_paragraph(fragments.units[idx], replacements)
        return loaded.source
    raise ValueError(f"Нет структурированной замены для {loaded.kind}")


def _replace_in_paragraph(paragraph, replacements: list[tuple[int, int, str]]) -> None:
    """Замена по локальным координатам с сохранением форматирования runs."""
    for start, stop, tag in sorted(replacements, key=lambda item: item[0], reverse=True):
        pos = 0
        spans = []
        for run in paragraph.runs:
            spans.append((run, pos, pos + len(run.text)))
            pos += len(run.text)
        affected = [(run, left, right) for run, left, right in spans if left < stop and start < right]
        if not affected:
            continue
        first_run, first_at, _ = affected[0]
        last_run, last_at, _ = affected[-1]
        head = first_run.text[: start - first_at]
        tail = last_run.text[stop - last_at:] if stop - last_at <= len(last_run.text) else ""
        if first_run is last_run:
            first_run.text = head + tag + tail
        else:
            first_run.text = head + tag
            for run, _, _ in affected[1:-1]:
                run.text = ""
            last_run.text = tail


def deanonymize_text(text: str, mapping: dict) -> tuple[str, list[str]]:
    """Замена тегов на исходные значения. Возвращает (текст, не найденные теги).

    Терпимо к искажениям LLM: `[ ФИО1 ]`, `[ФИО 1]`, `**[ФИО1]**`.
    Более длинные номера заменяются раньше коротких: `[ФИО10]` не станет `[ФИО1]0`.
    """
    items: list[tuple[str, str, str]] = []
    for tag, rec in mapping.get("tags", {}).items():
        match = re.match(r"([А-ЯЁA-Z]+)(\d+)", tag.strip("[]"))
        if not match:
            continue
        items.append((match.group(1), match.group(2), rec["canonical"]))
    items.sort(key=lambda item: (-len(item[1]), item[0]))
    out = text
    for label, num, canonical in items:
        pattern = re.compile(r"\[\s*" + re.escape(label) + r"\s*" + re.escape(num) + r"\s*\]")
        out = pattern.sub(lambda _m, value=canonical: value, out)
    leftover = sorted(set(re.findall(r"\[[А-ЯЁA-Z]+\s*\d+\]", out)))
    return out, leftover
