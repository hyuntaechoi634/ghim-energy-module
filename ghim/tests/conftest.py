"""Shared test fixtures."""

import sys
from pathlib import Path

# Ensure ghim is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
