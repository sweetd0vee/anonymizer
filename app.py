# -*- coding: utf-8 -*-
"""Веб-интерфейс анонимизатора на Streamlit."""
from __future__ import annotations

import base64
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
    icon_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "img", "sberbank.png")
    )
    if not os.path.exists(icon_path):
        return "📄"
    try:
        from PIL import Image
        return Image.open(icon_path)
    except Exception:
        return icon_path


def render_title() -> None:
    icon_path = os.path.join(os.path.dirname(__file__), "img", "anon.svg")
    with open(icon_path, encoding="utf-8") as f:
        icon_b64 = base64.b64encode(f.read().encode("utf-8")).decode("ascii")
    st.markdown(
        f'<div class="app-title">'
        f'<img src="data:image/svg+xml;base64,{icon_b64}" alt="" width="40" height="40" />'
        f"<h1>{APP_TITLE}</h1>"
        f"</div>",
        unsafe_allow_html=True,
    )


def main() -> None:
    page_icon = load_page_icon()
    st.set_page_config(page_title=APP_TITLE, layout="wide", page_icon=page_icon)
    inject_theme()
    render_title()
    init_state()
    tab_anon, tab_restore = st.tabs(["Обезличивание", "Восстановление"])
    with tab_anon:
        page_anonymize()
    with tab_restore:
        page_restore()


if __name__ == "__main__":
    main()
