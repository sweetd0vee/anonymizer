# -*- coding: utf-8 -*-
"""Чтение документов: TXT, DOCX, PDF (+ OCR для сканов без текстового слоя).

TXT
    utf-8-sig → utf-8 → cp1251; при неудаче — utf-8 с заменой символов.

DOCX
    Текст склеивается из абзацев тела, таблиц (включая вложенные) и колонтитулов,
    которые уже есть в файле. Пустые колонтитулы не создаются — иначе python-docx
    изменит документ при сохранении. Координаты сущностей считаются в этой склейке
    (`\\n` между абзацами), поэтому адрес, разрезанный на два абзаца, всё равно
    находится.

PDF
    Если на страницах в среднем меньше 25 символов текста — это скан, запускается
    Tesseract (`rus+eng`, PSM 4, 300 dpi). Иначе берётся текстовый слой.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field

from .ocr import ocr_page, resolve_tesseract

SUPPORTED_EXT = {".txt", ".docx", ".pdf"}
STRUCTURED_KINDS = frozenset({"docx"})

_HF_ATTRS = (
    "header", "footer",
    "first_page_header", "first_page_footer",
    "even_page_header", "even_page_footer",
)

__all__ = [
    "LoadedDoc",
    "STRUCTURED_KINDS",
    "SUPPORTED_EXT",
    "TextMap",
    "load",
    "load_from_bytes",
    "resolve_tesseract",
]


@dataclass
class TextMap:
    """Фрагменты документа и их позиции в тексте, склеенном через \\n."""

    texts: list[str] = field(default_factory=list)
    offsets: list[int] = field(default_factory=list)
    units: list = field(default_factory=list)

    def add(self, text: str, unit, *, skip_empty: bool = False) -> None:
        if skip_empty and not text:
            return
        offset = self.offsets[-1] + len(self.texts[-1]) + 1 if self.texts else 0
        self.texts.append(text)
        self.offsets.append(offset)
        self.units.append(unit)

    def joined(self) -> str:
        return "\n".join(self.texts)


@dataclass
class LoadedDoc:
    path: str
    kind: str            # txt | docx | pdf
    text: str
    source: object = None  # Document для DOCX
    fragments: TextMap | None = None
    ocr_used: bool = False
    warnings: list[str] = field(default_factory=list)


def load(path: str) -> LoadedDoc:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".txt":
        return _load_text(path)
    if ext == ".docx":
        return _load_docx(path)
    if ext == ".pdf":
        return _load_pdf(path)
    raise ValueError(f"Неподдерживаемый формат: {ext}")


def load_from_bytes(name: str, data: bytes) -> LoadedDoc:
    """Чтение загруженного файла (имя нужно только для расширения)."""
    ext = os.path.splitext(name)[1].lower()
    if ext not in SUPPORTED_EXT:
        raise ValueError(f"Неподдерживаемый формат: {ext or 'без расширения'}")
    if ext == ".docx":
        _validate_docx_bytes(data)
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, os.path.basename(name) or f"document{ext}")
        with open(path, "wb") as f:
            f.write(data)
        loaded = load(path)
        loaded.path = name
        return loaded


def _validate_docx_bytes(data: bytes) -> None:
    """Проверка, что файл — настоящий .docx, а не старый .doc под чужим именем."""
    if not data:
        raise ValueError("Файл пустой")
    if data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        raise ValueError(
            "Это старый формат Word (.doc). Откройте файл в Word и сохраните как .docx."
        )
    if not data.startswith(b"PK"):
        raise ValueError(
            "Файл не похож на документ Word (.docx). Проверьте формат или пересохраните в Word."
        )


def _load_text(path: str) -> LoadedDoc:
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return LoadedDoc(path, "txt", raw.decode(enc))
        except UnicodeDecodeError:
            continue
    return LoadedDoc(
        path, "txt", raw.decode("utf-8", errors="replace"),
        warnings=["Кодировка определена неточно, проверьте текст"],
    )


def _docx_containers(document):
    """Тело документа и колонтитулы, у которых уже есть своё содержимое.

    Нельзя просто взять section.header: python-docx при отсутствии определения
    создаёт пустую часть и при сохранении документ меняется.
    """
    yield document
    seen: set[int] = set()
    for section in document.sections:
        for attr in _HF_ATTRS:
            part = getattr(section, attr)
            if part.is_linked_to_previous:
                continue
            eid = id(part._element)
            if eid in seen:
                continue
            seen.add(eid)
            yield part


def _iter_paragraphs(container, _seen: set | None = None):
    """Все параграфы: тело, таблицы (рекурсивно), без дублей merged-ячеек."""
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    if _seen is None:
        _seen = set()
    for child in container.iter_inner_content():
        if isinstance(child, Paragraph):
            eid = id(child._element)
            if eid in _seen:
                continue
            _seen.add(eid)
            yield child
        elif isinstance(child, Table):
            seen_cells: set[int] = set()
            for row in child.rows:
                for cell in row.cells:
                    tc_id = id(cell._tc)
                    if tc_id in seen_cells:
                        continue
                    seen_cells.add(tc_id)
                    yield from _iter_paragraphs(cell, _seen)


def _load_docx(path: str) -> LoadedDoc:
    import docx
    document = docx.Document(path)
    fragments = TextMap()
    for src in _docx_containers(document):
        for para in _iter_paragraphs(src):
            fragments.add(para.text, para)
    return LoadedDoc(path, "docx", fragments.joined(), source=document, fragments=fragments)


def _load_pdf(path: str) -> LoadedDoc:
    import fitz  # pymupdf
    doc = fitz.open(path)
    pages = [page.get_text("text") for page in doc]
    total_chars = sum(len(p.strip()) for p in pages)
    warnings: list[str] = []
    ocr_used = False
    if total_chars < 25 * len(pages):
        tess, tessdata = resolve_tesseract()
        if tess is None:
            doc.close()
            raise RuntimeError(
                "PDF без текстового слоя (скан), а Tesseract OCR не найден. "
                "Установите Tesseract с языками rus+eng или загрузите PDF с текстом."
            )
        pages = []
        for i in range(len(doc)):
            page_text, ocr_err = ocr_page(doc, i, tess, tessdata)
            pages.append(page_text)
            if ocr_err:
                warnings.append(f"OCR, страница {i + 1}: {ocr_err}")
        ocr_used = True
        warnings.append("Текст получен через OCR — возможны ошибки распознавания")
    doc.close()
    return LoadedDoc(
        path, "pdf", "\n\n".join(p.strip() for p in pages),
        ocr_used=ocr_used, warnings=warnings,
    )
