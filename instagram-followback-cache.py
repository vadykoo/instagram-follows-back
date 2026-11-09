#!/usr/bin/env python3
"""Deprecated. Use `python3 app.py` instead — UI + cache on one localhost port."""
from __future__ import annotations

import sys

print(
    "instagram-followback-cache.py is obsolete.\n"
    "Run:  python3 app.py\n"
    "Then open the printed http://127.0.0.1:…/ URL.",
    file=sys.stderr,
)
sys.exit(1)
