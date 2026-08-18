# -*- coding: utf-8 -*-
"""NER на базе Natasha: ФИО, организации. Модели локальные, работают офлайн."""
from __future__ import annotations

import re

from .entities import Entity

# Организации, которые обычно не нужно обезличивать (суды и т.п. нужны для анализа)
SKIP_ORG = re.compile(
    r"(суд|судебн|прокуратур|росреестр|федеральн\w+ служб|казначейств)", re.IGNORECASE
)

# Мусорные PER-спаны: одиночные инициалы и т.п.
MIN_PER_LEN = 4


class NerEngine:
    """Ленивая обёртка над Natasha: модели грузятся при первом вызове (~5-10 сек)."""

    def __init__(self):
        self._ready = False

    def _ensure(self):
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

        out: list[Entity] = []
        for span in doc.spans:
            if span.type == "PER":
                if len(span.text) < MIN_PER_LEN:
                    continue
                key = self._person_key(span)
                out.append(Entity("FIO", span.start, span.stop, span.text, key,
                                  norm_text=getattr(span, "normal", "") or span.text))
            elif span.type == "ORG":
                if SKIP_ORG.search(span.text):
                    continue
                try:
                    span.normalize(self._morph_vocab)
                    key = (span.normal or span.text).lower()
                except Exception:
                    key = span.text.lower()
                out.append(Entity("ORG", span.start, span.stop, span.text, key))
            # LOC пропускаем: города/регионы нужны для юр. анализа,
            # адреса ловит регулярка, остальное можно добавить вручную
        return self._merge_adjacent_fio(out, text)

    def _merge_adjacent_fio(self, entities: list[Entity], text: str) -> list[Entity]:
        """NER иногда делит «Иванов И.П.» на два спана — склеиваем соседние ФИО."""
        fio = sorted((e for e in entities if e.type == "FIO"), key=lambda e: e.start)
        other = [e for e in entities if e.type != "FIO"]
        merged: list[Entity] = []
        for e in fio:
            if merged:
                prev = merged[-1]
                gap = text[prev.stop:e.start]
                if len(gap) <= 1 and (not gap or gap.isspace()):
                    mtext = text[prev.start:e.stop]
                    key = (prev.norm_key if "|" in prev.norm_key
                           else e.norm_key if "|" in e.norm_key
                           else self._key_from_text(mtext) or prev.norm_key)
                    norm = f"{prev.norm_text or prev.text} {e.norm_text or e.text}"
                    merged[-1] = Entity("FIO", prev.start, e.stop, mtext, key,
                                        norm_text=norm)
                    continue
            merged.append(e)
        return other + merged

    def _key_from_text(self, fragment: str) -> str | None:
        try:
            m = self._names.find(fragment)
        except Exception:
            return None
        if m and m.fact:
            return _person_norm_key(
                getattr(m.fact, "last", None),
                getattr(m.fact, "first", None),
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
            d = fact.as_dict
            key = _person_norm_key(d.get("last"), d.get("first"))
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
    """Склейка «голая фамилия» -> «фамилия|инициал», если вариант один.

    Пример: «Иванов» без имени получит тот же тег, что «Иванов Иван Петрович»,
    если в документе нет второго Иванова с другим инициалом.
    """
    fio = [e for e in entities if e.type == "FIO"]
    composite = {}  # фамилия -> set(полных ключей 'фамилия|и')
    for e in fio:
        if "|" in e.norm_key:
            composite.setdefault(e.norm_key.split("|")[0], set()).add(e.norm_key)
    for e in fio:
        if "|" not in e.norm_key:
            variants = composite.get(e.norm_key)
            if variants and len(variants) == 1:
                e.norm_key = next(iter(variants))
