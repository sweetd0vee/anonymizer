# -*- coding: utf-8 -*-
"""Сохранение результатов обезличивания и восстановления."""
from __future__ import annotations

import io
import os

from . import engine
from .entities import Entity
from .readers import STRUCTURED_KINDS, LoadedDoc


def anon_output_path(src_path: str, out_dir: str | None = None) -> str:
    """file.docx -> file_anon.docx; pdf/txt -> file_anon.docx."""
    folder, name = os.path.split(src_path)
    base, _ = os.path.splitext(name)
    return os.path.join(out_dir or folder, f"{base}_anon.docx")


def restored_output_path(src_path: str) -> str:
    folder, name = os.path.split(src_path)
    base, _ = os.path.splitext(name)
    return os.path.join(folder, f"{base.replace('_anon', '').replace('.anon', '')}_restored.docx")


def anonymized_bytes(loaded: LoadedDoc, entities: list[Entity], out_path: str) -> bytes:
    ext = os.path.splitext(out_path)[1].lower().lstrip(".")
    if loaded.kind in STRUCTURED_KINDS and ext == loaded.kind:
        buf = io.BytesIO()
        engine.anonymize_document(loaded, entities).save(buf)
        return buf.getvalue()
    text = engine.anonymize_text(loaded.text, entities)
    return text_bytes(text, out_path)


def save_anonymized(loaded: LoadedDoc, entities: list[Entity], out_path: str) -> None:
    with open(out_path, "wb") as f:
        f.write(anonymized_bytes(loaded, entities, out_path))


def text_bytes(text: str, out_path: str) -> bytes:
    if out_path.lower().endswith(".docx"):
        import docx
        document = docx.Document()
        for line in text.split("\n"):
            document.add_paragraph(line)
        buf = io.BytesIO()
        document.save(buf)
        return buf.getvalue()
    return text.encode("utf-8")
