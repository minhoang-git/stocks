"""Vercel WSGI entry point.

Vercel imports this module for each serverless instance. The protected GitHub
Actions endpoint performs scheduled refreshes, so no background thread is
started here.
"""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from finance_app.app import create_app


app = create_app(start_scheduler=False)
