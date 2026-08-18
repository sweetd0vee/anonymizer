# -*- coding: utf-8 -*-
"""Веб-интерфейс анонимизатора на Streamlit."""
from __future__ import annotations

import os

import streamlit as st

from ui.constants import APP_TITLE
from ui.pages import page_anonymize, page_restore
from ui.state import init_state


def inject_theme() -> None:
    css_path = os.path.join(os.path.dirname(__file__), "frontend", "theme.css")
    with open(css_path, encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


def load_page_icon():
    icon_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "sberbank.png"))
    if not os.path.exists(icon_path):
        return "📄"
    try:
        from PIL import Image
        return Image.open(icon_path)
    except Exception:
        return icon_path


def main() -> None:
    page_icon = load_page_icon()
    st.set_page_config(page_title=APP_TITLE, layout="wide", page_icon=page_icon)
    inject_theme()
    st.title(APP_TITLE)
    init_state()
    tab_anon, tab_restore = st.tabs(["Обезличивание", "Восстановление"])
    with tab_anon:
        page_anonymize()
    with tab_restore:
        page_restore()


if __name__ == "__main__":
    main()
