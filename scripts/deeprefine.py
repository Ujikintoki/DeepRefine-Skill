#!/usr/bin/env python3
"""Backward-compatible entry: prefer `deeprefine` on PATH after pip install -e."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]  # DeepRefine-Skill repo root
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from deeprefine_skill.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
