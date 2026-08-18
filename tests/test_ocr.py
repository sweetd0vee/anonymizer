# -*- coding: utf-8 -*-
"""Тест OCR на встроенном движке: синтетический скан A4 -> распознавание."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from anon import engine, readers
from anon.entities import TagRegistry

TEXT = (
    "Договор поставки № 17.\n\n"
    "Поставщик: ООО «Ромашка», ИНН 7707083893.\n"
    "Директор Иванов Иван Петрович.\n"
    "Телефон: +7 (916) 123-45-67."
)


def make_scan(path: str):
    """Нормальный A4-скан: текст -> растр -> картинка на всю A4-страницу.

    insert_htmlbox корректно рендерит кириллицу (в отличие от insert_textbox
    с fontfile, который в некоторых версиях PyMuPDF ставит '?' вместо глифов).
    """

    import fitz

    src = fitz.open()
    page = src.new_page(width=595, height=842)  # A4 в пунктах
    html = (
        "<div style='font-family:sans-serif;font-size:15px;"
        "line-height:1.6'>"
        + TEXT.replace("\n", "<br>")
        + "</div>"
    )
    page.insert_htmlbox(fitz.Rect(60, 70, 535, 500), html)
    pix = page.get_pixmap(dpi=200)
    out = fitz.open()
    op = out.new_page(width=595, height=842)
    op.insert_image(op.rect, pixmap=pix)  # картинка на всю страницу, текст-слоя нет
    out.save(path)
    src.close()
    out.close()


def main():
    exe, tessdata = readers.resolve_tesseract()
    print("Движок OCR:", exe)
    print("tessdata:", tessdata)
    assert exe, "движок OCR не найден"

    scan = os.path.join(os.path.dirname(__file__), "scan.pdf")
    make_scan(scan)

    loaded = readers.load(scan)
    print("OCR использован:", loaded.ocr_used)
    print("Распознано:\n", loaded.text)
    assert loaded.ocr_used, "OCR не сработал (найден текстовый слой?)"
    for needed in ("Иванов", "Ромашка", "7707083893"):
        assert needed in loaded.text, f"OCR не распознал: {needed}"

    # распознанный скан обезличивается как обычный текст
    analyzer = engine.Analyzer()
    ents = analyzer.detect(loaded.text)
    reg = TagRegistry()
    engine.apply_tags(ents, reg)
    anon = engine.anonymize_text(loaded.text, ents)
    print("\nОбезличенный распознанный текст:\n", anon)
    assert "Иванов" not in anon and "7707083893" not in anon

    print("\nOCR: ok")


if __name__ == "__main__":
    main()

