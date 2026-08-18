# -*- coding: utf-8 -*-
"""NER на базе Natasha: ФИО и организации. Модели локальные, работают офлайн.

Что берём
---------
PER  — ФИО длиннее 3 символов. Соседние спаны («Иванов» + «И.П.») склеиваются.
       Ключ группировки: `фамилия|первый_инициал`, чтобы «Иванов И.П.» и
       «Иванову Ивану Петровичу» получили один тег. Голая фамилия подтягивается
       к полному ключу, если в документе нет однофамильца с другим инициалом.
ORG  — кроме судов, прокуратуры, Росреестра, казначейства и «федеральных служб»
       (они нужны для юридического анализа и не обезличиваются).

Что не берём
------------
LOC  — города и регионы оставляет NER как есть: они нужны в резолютивной части.
       Конкретные адреса ловит регулярка, остальное можно добавить вручную.
"""
from __future__ import annotations

import re

from .entities import Entity

SKIP_ORG = re.compile(
    r"(суд|судебн|прокуратур|росреестр|федеральн\w+ служб|казначейств)", re.IGNORECASE
)

# Мусорные PER-спаны: одиночные инициалы и т.п.
MIN_PER_LEN = 4


class NerEngine:
    """Ленивая обёртка над Natasha: модели грузятся при первом вызове (~5–10 сек)."""

    def __init__(self) -> None:
        self._ready = False

    def _ensure(self) -> None:
        if self._ready:
            return
        from natasha import (
            Segmenter, MorphVocab, NewsEmbedding,
            NewsMorphTagger, NewsNERTagger, NamesExtractor, Doc,
        )
        self._Doc = Doc
        self._segmenter = Segmenter()
        self._morph_vocab = MorphVocab()
        emb = NewsEmbedding()
        self._morph_tagger = NewsMorphTagger(emb)
        self._ner_tagger = NewsNERTagger(emb)
        self._names = NamesExtractor(self._morph_vocab)
        self._ready = True

    def detect(self, text: str) -> list[Entity]:
        self._ensure()
        doc = self._Doc(text)
        doc.segment(self._segmenter)
        if not doc.tokens:
            return []
        doc.tag_morph(self._morph_tagger)
        doc.tag_ner(self._ner_tagger)
        out = [entity for span in doc.spans if (entity := self._from_span(span))]
        return self._merge_adjacent_fio(out, text)

    def _from_span(self, span) -> Entity | None:
        if span.type == "PER":
            return self._person_entity(span)
        if span.type == "ORG":
            return self._org_entity(span)
        return None

    def _person_entity(self, span) -> Entity | None:
        if len(span.text) < MIN_PER_LEN:
            return None
        return Entity(
            "FIO", span.start, span.stop, span.text, self._person_key(span),
            norm_text=getattr(span, "normal", "") or span.text,
        )

    def _org_entity(self, span) -> Entity | None:
        if SKIP_ORG.search(span.text):
            return None
        try:
            span.normalize(self._morph_vocab)
            key = (span.normal or span.text).lower()
        except Exception:
            key = span.text.lower()
        return Entity("ORG", span.start, span.stop, span.text, key)

    def _merge_adjacent_fio(self, entities: list[Entity], text: str) -> list[Entity]:
        """NER иногда делит «Иванов И.П.» на два спана — склеиваем соседние ФИО."""
        fio = sorted((e for e in entities if e.type == "FIO"), key=lambda e: e.start)
        other = [e for e in entities if e.type != "FIO"]
        merged: list[Entity] = []
        for entity in fio:
            if merged and self._adjacent(merged[-1], entity, text):
                merged[-1] = self._join_fio(merged[-1], entity, text)
            else:
                merged.append(entity)
        return other + merged

    def _adjacent(self, prev: Entity, entity: Entity, text: str) -> bool:
        gap = text[prev.stop:entity.start]
        return len(gap) <= 1 and (not gap or gap.isspace())

    def _join_fio(self, prev: Entity, entity: Entity, text: str) -> Entity:
        merged_text = text[prev.start:entity.stop]
        if "|" in prev.norm_key:
            key = prev.norm_key
        elif "|" in entity.norm_key:
            key = entity.norm_key
        else:
            key = self._key_from_text(merged_text) or prev.norm_key
        norm = f"{prev.norm_text or prev.text} {entity.norm_text or entity.text}"
        return Entity("FIO", prev.start, entity.stop, merged_text, key, norm_text=norm)

    def _key_from_text(self, fragment: str) -> str | None:
        try:
            match = self._names.find(fragment)
        except Exception:
            return None
        if match and match.fact:
            return _person_norm_key(
                getattr(match.fact, "last", None),
                getattr(match.fact, "first", None),
            )
        return None

    def _person_key(self, span) -> str:
        """Ключ группировки: фамилия + первый инициал (лемматизированные)."""
        try:
            span.normalize(self._morph_vocab)
            span.extract_fact(self._names)
        except Exception:
            return span.text.lower()
        fact = getattr(span, "fact", None)
        if fact is not None:
            data = fact.as_dict
            key = _person_norm_key(data.get("last"), data.get("first"))
            if key:
                return key
        return (span.normal or span.text).lower()


def _person_norm_key(last: str | None, first: str | None) -> str | None:
    last = (last or "").lower()
    first = first or ""
    if not last:
        return None
    return f"{last}|{first[:1].lower()}" if first else last


def merge_person_keys(entities: list[Entity]) -> None:
    """Склейка «голая фамилия» → «фамилия|инициал», если вариант один.

    Пример: «Иванов» без имени получит тот же тег, что «Иванов Иван Петрович»,
    если в документе нет второго Иванова с другим инициалом.
    """
    fio = [e for e in entities if e.type == "FIO"]
    composite: dict[str, set[str]] = {}
    for entity in fio:
        if "|" in entity.norm_key:
            composite.setdefault(entity.norm_key.split("|")[0], set()).add(entity.norm_key)
    for entity in fio:
        if "|" not in entity.norm_key:
            variants = composite.get(entity.norm_key)
            if variants and len(variants) == 1:
                entity.norm_key = next(iter(variants))
