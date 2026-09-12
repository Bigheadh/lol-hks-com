"""Read-only bundled resources and persistent, writable per-user storage."""
import os
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
if FROZEN:
    CACHE_ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Hexassist" / "cache"
else:
    CACHE_ROOT = RESOURCE_ROOT / ".cache"
SEED_ROOT = RESOURCE_ROOT / "seed" if FROZEN else None
