import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for p in (ROOT, ROOT / "MI_auto", ROOT / "MI_SELLERSPRITE"):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)
