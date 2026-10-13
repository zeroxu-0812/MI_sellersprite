import json
import pytest
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(PROJECT))
from run_all import resolve_category, list_categories, CategoryNotFound

DICT = str(PROJECT / "categories.json")


def test_exact_match():
    assert resolve_category("water bottles", DICT) == "3773431"


def test_alias_match():
    assert resolve_category("运动水杯", DICT) == "3773431"
    assert resolve_category("水瓶", DICT) == "3773431"


def test_case_insensitive():
    assert resolve_category("Water Bottles", DICT) == "3773431"


def test_not_found_raises():
    with pytest.raises(CategoryNotFound):
        resolve_category("不存在的类目xyz", DICT)


def test_list_categories_keyword():
    rows = list_categories("water", DICT)
    assert any(r["id"] == "3773431" for r in rows)


def test_list_categories_empty_keyword_returns_all():
    rows = list_categories("", DICT)
    assert len(rows) >= 1
