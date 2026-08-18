# -*- coding: utf-8 -*-
"""Запуск веб-приложения: python -m anon"""
from __future__ import annotations

import os
import subprocess
import sys


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app = os.path.join(root, "app.py")
    raise SystemExit(subprocess.call(
        [sys.executable, "-m", "streamlit", "run", app],
        cwd=root,
    ))


if __name__ == "__main__":
    main()
