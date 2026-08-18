# -*- coding: utf-8 -*-
"""Сохранение результатов обезличивания и восстановления.

Формат по умолчанию:
- PDF → PDF (новый файл из обезличенного текста, исходная вёрстка не копируется);
- DOCX → DOCX с сохранением runs/таблиц/колонтитулов;
- TXT → DOCX.
При скачивании формат можно сменить на PDF, DOCX или TXT.
"""
from __future__ import annotations

import html
import io
import os

from .entities import Entity
from .readers import STRUCTURED_KINDS, LoadedDoc
from .replace import anonymize_document, anonymize_text


def _normalized_ext(override: str | None, default: str) -> str:
    if not override:
        return default
    return override if override.startswith(".") else f".{override}"


def anon_output_path(
    src_path: str, out_dir: str | None = None, ext: str | None = None,
) -> str:
    """Имя обезличенного файла. ext: '.pdf' | '.docx' | '.txt' или None (по источнику)."""
    folder, name = os.path.split(src_path)
    base, src_ext = os.path.splitext(name)
    default = ".pdf" if src_ext.lower() == ".pdf" else ".docx"
    out_ext = _normalized_ext(ext, default)
    return os.path.join(out_dir or folder, f"{base}_anon{out_ext.lower()}")


def restored_output_path(src_path: str, ext: str | None = None) -> str:
    folder, name = os.path.split(src_path)
    base, src_ext = os.path.splitext(name)
    for suffix in ("_anon", ".anon", "_restored"):
        base = base.replace(suffix, "")
    src_ext = src_ext.lower()
    default = src_ext if src_ext in {".pdf", ".txt"} else ".docx"
    out_ext = _normalized_ext(ext, default)
    return os.path.join(folder, f"{base}_restored{out_ext.lower()}")


def anonymized_bytes(loaded: LoadedDoc, entities: list[Entity], out_path: str) -> bytes:
    ext = os.path.splitext(out_path)[1].lower().lstrip(".")
    if loaded.kind in STRUCTURED_KINDS and ext == loaded.kind:
        buf = io.BytesIO()
        anonymize_document(loaded, entities).save(buf)
        return buf.getvalue()
    text = anonymize_text(loaded.text, entities)
    return text_bytes(text, out_path)


def save_anonymized(loaded: LoadedDoc, entities: list[Entity], out_path: str) -> None:
    with open(out_path, "wb") as f:
        f.write(anonymized_bytes(loaded, entities, out_path))


def text_bytes(text: str, out_path: str) -> bytes:
    ext = os.path.splitext(out_path)[1].lower()
    if ext == ".docx":
        import docx
        document = docx.Document()
        for line in text.split("\n"):
            document.add_paragraph(line)
        buf = io.BytesIO()
        document.save(buf)
        return buf.getvalue()
    if ext == ".pdf":
        return pdf_from_text(text)
    return text.encode("utf-8")


def pdf_from_text(text: str) -> bytes:
    """Новый PDF из обезличенного текста (кириллица через Story/HTML)."""
    import fitz

    body = html.escape(text.replace("\r\n", "\n").replace("\r", "\n"))
    body = body.replace("\n", "<br>")
    html_doc = (
        "<div style='font-family:sans-serif;font-size:12px;line-height:1.45'>"
        f"{body}</div>"
    )
    mediabox = fitz.paper_rect("a4")
    where = mediabox + (50, 50, -50, -50)
    story = fitz.Story(html_doc)
    buf = io.BytesIO()
    writer = fitz.DocumentWriter(buf)
    more = True
    pages = 0
    while more:
        device = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(device)
        writer.end_page()
        pages += 1
        if pages >= 500:
            break
    writer.close()
    return buf.getvalue()
