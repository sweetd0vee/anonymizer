# -*- coding: utf-8 -*-
"""Экспорт обезличенных файлов и выбор формата скачивания."""
from __future__ import annotations

import json
import os
import zipfile
from io import BytesIO

import streamlit as st

from anon import readers, writers
from anon.entities import TagRegistry

from .constants import DOWNLOAD_FORMATS, EXT_FORMAT, FORMAT_EXT, MIME
from .state import FileState, used_tags


def mapping_json() -> bytes:
    registry: TagRegistry = st.session_state.registry
    mapping = registry.to_mapping(
        [fs.name for fs in st.session_state.files if not fs.error],
        include=used_tags(),
    )
    return json.dumps(mapping, ensure_ascii=False, indent=2).encode("utf-8")


def format_from_files(files: list[FileState]) -> str:
    for fs in files:
        if fs.error:
            continue
        label = EXT_FORMAT.get(os.path.splitext(fs.name)[1].lower())
        if label:
            return label
    return "DOCX"


def export_file(fs: FileState, ext: str | None = None) -> tuple[str, bytes]:
    out_name = os.path.basename(writers.anon_output_path(fs.name, ext=ext))
    loaded = readers.load_from_bytes(fs.name, fs.raw)
    return out_name, writers.anonymized_bytes(loaded, fs.entities, out_name)


def export_zip(fmt: str | None = None) -> bytes:
    ext = FORMAT_EXT.get(fmt or "", ".docx")
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fs in st.session_state.files:
            if fs.error:
                continue
            name, data = export_file(fs, ext)
            zf.writestr(name, data)
        zf.writestr("_mapping.json", mapping_json())
    return buf.getvalue()


def mime_for(name: str) -> str:
    return MIME.get(os.path.splitext(name)[1].lower(), "application/octet-stream")


def render_download_format(key: str):
    fmt_col, btn_col = st.columns(2, vertical_alignment="bottom", gap=None)
    with fmt_col:
        selected = st.selectbox(
            "Формат",
            options=DOWNLOAD_FORMATS,
            key=key,
            width=108,
        )
    return selected, btn_col
