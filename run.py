#!/usr/bin/env python3
"""
Chạy API local — không phụ thuộc cwd.

  cd backend && python run.py

hoặc từ thư mục gốc dự án:

  python backend/run.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=[str(_BACKEND / "app")],
    )
