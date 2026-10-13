import sys
from pathlib import Path
import pytest

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "MI_auto"))


@pytest.fixture(scope="session")
def raw_json_path():
    p = PROJECT / "MI_SELLERSPRITE" / "output" / "sports_water_bottles_raw.json"
    if not p.exists():
        pytest.skip(f"fixture 缺失: {p}")
    return p
