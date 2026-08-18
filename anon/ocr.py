# -*- coding: utf-8 -*-
"""Поиск Tesseract и распознавание страницы PDF-скана."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

TESSERACT_CANDIDATES = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)


def resolve_tesseract() -> tuple[str | None, str | None]:
    """Возвращает (путь к tesseract.exe, папка tessdata или None).

    Приоритет у встроенного движка (vendor/tesseract), затем системная установка.
    """
    vendor = os.path.join(os.path.dirname(os.path.dirname(__file__)), "vendor", "tesseract")
    bundled = os.path.join(vendor, "tesseract.exe")
    if os.path.exists(bundled):
        tessdata = os.path.join(vendor, "tessdata")
        return bundled, (tessdata if os.path.isdir(tessdata) else None)
    found = shutil.which("tesseract")
    if found:
        return found, None
    for candidate in TESSERACT_CANDIDATES:
        if os.path.exists(candidate):
            return candidate, None
    return None, None


def ocr_page(doc, page_index: int, tesseract: str,
             tessdata: str | None = None) -> tuple[str, str | None]:
    """Распознать одну страницу: (текст, текст ошибки или None)."""
    page = doc[page_index]
    pix = page.get_pixmap(dpi=300)
    with tempfile.TemporaryDirectory() as td:
        img = os.path.join(td, "page.png")
        pix.save(img)
        cmd = [tesseract, img, "stdout", "-l", "rus+eng", "--psm", "4"]
        if tessdata:
            cmd += ["--tessdata-dir", tessdata]
        res = subprocess.run(
            cmd, capture_output=True, timeout=180,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    text = res.stdout.decode("utf-8", errors="replace")
    if res.returncode == 0:
        return text, None
    err = res.stderr.decode("utf-8", errors="replace").strip()
    if text.strip():
        return text, err or f"Tesseract вернул код {res.returncode}"
    return "", err or f"Tesseract не распознал страницу (код {res.returncode})"
