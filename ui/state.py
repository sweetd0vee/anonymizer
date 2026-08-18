# -*- coding: utf-8 -*-
"""Состояние сессии Streamlit: файлы, теги, ручные сущности."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import streamlit as st

from anon import config, engine, readers
from anon.entities import Entity, TagRegistry

from .constants import AVAILABLE_TYPES


def count_words(text: str) -> int:
    return len(text.split()) if text else 0


@dataclass
class FileState:
    name: str
    raw: bytes
    text: str = ""
    warnings: list[str] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)
    error: str = ""


@st.cache_resource
def get_analyzer() -> engine.Analyzer:
    return engine.Analyzer()


def init_state() -> None:
    st.session_state.setdefault("files", [])
    st.session_state.setdefault("editor_rev", 0)
    st.session_state.setdefault("restore_text", "")
    st.session_state.setdefault("restore_name", "")
    st.session_state.setdefault("restore_leftover", [])
    if "registry" not in st.session_state:
        st.session_state.registry = TagRegistry()
    if "enabled_types" not in st.session_state:
        saved = config.load_settings().get("enabled_types")
        types = (set(saved) & AVAILABLE_TYPES) if saved else set(AVAILABLE_TYPES)
        st.session_state.enabled_types = types | {"OTHER"}


def apply_enabled_types() -> None:
    types = st.session_state.enabled_types | {"OTHER"}
    for fs in st.session_state.files:
        for entity in fs.entities:
            if entity.source == "auto":
                entity.enabled = entity.type in types


def analyze_uploads(uploads) -> tuple[list[FileState], TagRegistry]:
    analyzer = get_analyzer()
    files: list[FileState] = []
    for up in uploads:
        name = os.path.basename(up.name)
        fs = FileState(name=name, raw=up.getvalue())
        try:
            loaded = readers.load_from_bytes(name, fs.raw)
            fs.text = loaded.text
            fs.warnings = loaded.warnings
            fs.entities = [
                entity for entity in analyzer.detect(loaded.text)
                if entity.type in AVAILABLE_TYPES
            ]
        except Exception as exc:
            fs.error = str(exc)
        files.append(fs)
    registry = TagRegistry()
    engine.apply_package_tags([fs.entities for fs in files], registry)
    enabled = st.session_state.enabled_types | {"OTHER"}
    for fs in files:
        for entity in fs.entities:
            entity.enabled = entity.type in enabled
    return files, registry


def set_tag_enabled(tag: str, enabled: bool) -> None:
    for fs in st.session_state.files:
        for entity in fs.entities:
            if entity.tag == tag:
                entity.enabled = enabled


def add_manual(fragment: str, etype: str) -> tuple[int, str]:
    fragment = fragment.strip()
    if len(fragment) < 2:
        return 0, "empty"
    added = 0
    seen = 0
    registry: TagRegistry = st.session_state.registry
    for fs in st.session_state.files:
        if not fs.text:
            continue
        hits = engine.find_manual_occurrences(fs.text, fragment)
        seen += len(hits)
        for start, stop in hits:
            cand = Entity(etype, start, stop, fragment,
                          norm_key=fragment.lower(), source="manual")
            clash = [x for x in fs.entities if x.overlaps(cand)]
            if any(x.enabled for x in clash):
                continue
            for x in clash:
                fs.entities.remove(x)
            registry.assign(cand)
            fs.entities.append(cand)
            added += 1
        fs.entities.sort(key=lambda x: x.start)
    if added:
        return added, "ok"
    return 0, "not_found" if seen == 0 else "overlap"


def used_tags() -> set[str]:
    return {entity.tag for fs in st.session_state.files
            for entity in fs.entities if entity.enabled and entity.tag}
