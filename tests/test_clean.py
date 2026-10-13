import json
import pytest
from stages import clean


def _item(asin, dks):
    # dks: {dk: sales}
    return {"asin": asin, "brand": "B", "price": 10, "rating": 4.5,
            "reviews": 100, "available_days": 30,
            "amz_unit_trends": [{"dk": dk, "sales": s} for dk, s in dks.items()]}


def test_shift_month():
    assert clean.shift_month("202605", -23) == "202406"
    assert clean.shift_month("202601", -23) == "202402"
    assert clean.shift_month("202612", -23) == "202501"


def test_window_is_24_months():
    data = [_item("A", {"202401": 1, "202605": 9})]
    start, end = clean.window_for(data)
    assert end == "202605"
    assert start == "202406"  # 202605 - 23 月


def test_run_filters_to_24_months(tmp_path):
    # 造 30 个月趋势（202312 ~ 202605），最新月 202605 → 窗口 202406~202605
    dks = {f"{y}{m:02d}": 1 for y in (2023, 2024, 2025, 2026)
           for m in range(1, 13) if not (y == 2023 and m < 12) and not (y == 2026 and m > 5)}
    data = [_item("A", dks)]
    # 跑 clean.run 需要 run_dir；用 run_dir.new_run_dir 建
    from run_dir import new_run_dir
    p = new_run_dir("US", "X", base=tmp_path)
    p.raw_json.write_text(json.dumps(data), encoding="utf-8")
    clean.run(p)
    import pandas as pd
    df = pd.read_excel(p.input_xlsx, engine="openpyxl")
    months = sorted(df["时间"].unique())
    assert months[0] == "2024-06"
    assert months[-1] == "2026-05"
    assert len(months) <= 24
    # 2023-12 行应被裁掉
    assert "2023-12" not in months


def test_run_includes_no_trends_product(tmp_path):
    data = [_item("A", {}), _item("B", {"202605": 5})]  # A 无 trends
    from run_dir import new_run_dir
    p = new_run_dir("US", "X", base=tmp_path)
    p.raw_json.write_text(json.dumps(data), encoding="utf-8")
    clean.run(p)
    import pandas as pd
    df = pd.read_excel(p.input_xlsx, engine="openpyxl")
    assert "A" in set(df["ASIN"])  # 零销量占位行进表
    meta = json.loads(p.clean_meta.read_text(encoding="utf-8"))
    assert meta["month_count"] == 24
    assert meta["window_end"] == "2026-05"


def test_run_raises_when_all_products_no_trends(tmp_path):
    """全部产品 amz_unit_trends 为空 → 无有效 dk → window_for 返 (None,None) → run() raise RuntimeError。"""
    data = [_item("A", {})]  # 仅一个 ASIN，trends 为空
    from run_dir import new_run_dir
    p = new_run_dir("US", "X", base=tmp_path)
    p.raw_json.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RuntimeError):
        clean.run(p)
