# -*- coding: utf-8 -*-
"""Подсветка сущностей и Streamlit-компонент превью."""
from __future__ import annotations

import html
import os

import streamlit.components.v1 as components

from anon import engine
from anon.entities import ENTITY_TYPES, Entity

from .constants import COLORS

_PREVIEW_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "frontend", "preview",
)
_preview_component = components.declare_component("anon_preview", path=_PREVIEW_DIR)


def highlight_html(text: str, entities: list[Entity], show_result: bool) -> str:
    if show_result:
        body = html.escape(engine.anonymize_text(text, entities))
        return body.replace("\n", "<br>")
    parts = []
    last = 0
    for entity in sorted(entities, key=lambda item: item.start):
        parts.append(html.escape(text[last:entity.start]))
        color = COLORS.get(entity.type, "#eeeeee") if entity.enabled else "#f0f0f0"
        style = f"background:{color};padding:0 3px;border-radius:3px;"
        if not entity.enabled:
            style += "text-decoration:line-through;color:#888;"
        title = html.escape(entity.tag or ENTITY_TYPES.get(entity.type, entity.type))
        parts.append(
            f'<mark style="{style}" title="{title}">{html.escape(entity.text)}</mark>'
        )
        last = entity.stop
    parts.append(html.escape(text[last:]))
    return "".join(parts).replace("\n", "<br>")


def render_preview(body: str, key: str) -> str:
    value = _preview_component(html=body, key=key, default="")
    return (value or "").strip()
