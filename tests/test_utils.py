import sys
from datetime import date
from pathlib import Path
import pytest

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
from run_all import currency_for, infer_crawl_date, recommend_bands


def test_currency_map():
    assert currency_for("US") == "$"
    assert currency_for("UK") == "£"
    assert currency_for("DE") == "€"
    assert currency_for("JP") == "¥"
    assert currency_for("CA") == "C$"
    assert currency_for("xx") == "$"  # 未知市场回退美元


def test_infer_crawl_date():
    data = [{"asin": "A", "amz_unit_trends": [{"dk": "202406", "sales": 1},
                                              {"dk": "202606", "sales": 2}]},
            {"asin": "B", "amz_unit_trends": [{"dk": "202501", "sales": 3}]}]
    # 最晚月 202606 → 次月初 2026-07-01
    assert infer_crawl_date(data) == date(2026, 7, 1)


def test_infer_crawl_date_dec_rollover():
    data = [{"asin": "A", "amz_unit_trends": [{"dk": "202612", "sales": 1}]}]
    assert infer_crawl_date(data) == date(2027, 1, 1)


def test_infer_crawl_date_skips_invalid_dk():
    """非法 dk（非数字 / 月份越界）应被跳过，仍能从合法 dk 推断采集日。"""
    data = [{"asin": "A", "amz_unit_trends": [
        {"dk": "202613", "sales": 1},   # 月份 13 越界
        {"dk": "2026ab", "sales": 2},   # 非数字
        {"dk": "20265", "sales": 3},    # 非 6 位
        {"dk": "202501", "sales": 4},   # 合法
    ]}]
    # 仅 202501 合法 → 次月初 2025-02-01；不抛异常
    assert infer_crawl_date(data) == date(2025, 2, 1)


def test_infer_crawl_date_all_invalid_falls_back_today():
    """全部 dk 非法时回退 date.today()，不崩溃。"""
    data = [{"asin": "A", "amz_unit_trends": [
        {"dk": "202613", "sales": 1},
        {"dk": "2026ab", "sales": 2},
    ]}]
    assert infer_crawl_date(data) == date.today()


def test_recommend_bands(tmp_path):
    import pandas as pd
    xlsx = tmp_path / "in.xlsx"
    # 10 个 ASIN，价格 10..19 → 四分位 12/14/16
    rows = [{"ASIN": f"B00{i}", "Brand": "X", "Price": 10 + i,
             "Ratings": 4.0, "Review Count": 10, "Creation date": "2024-01-01",
             "Unit Sales": 100, "Total Revenue": 1000, "时间": "2025-01"} for i in range(10)]
    pd.DataFrame(rows).to_excel(xlsx, index=False)
    bands = recommend_bands(str(xlsx))
    assert len(bands) == 3
    assert all(isinstance(b, int) for b in bands)
    assert bands == sorted(bands)


def test_recommend_bands_all_nan_price_returns_default(tmp_path):
    """价格全 NaN（如 no-trends 占位行）→ 回退 [10,20,30]，不抛异常。"""
    import pandas as pd
    xlsx = tmp_path / "nan.xlsx"
    rows = [{"ASIN": "B0001", "Brand": "X", "Price": None,
             "Ratings": None, "Review Count": None, "Creation date": None,
             "Unit Sales": None, "Total Revenue": None, "时间": "2025-01"}]
    pd.DataFrame(rows).to_excel(xlsx, index=False, engine="openpyxl")
    bands = recommend_bands(str(xlsx))
    assert bands == [10, 20, 30]


def test_recommend_bands_normal_returns_three_ints(tmp_path):
    """正常价格 xlsx → 3 个升序 int。"""
    import pandas as pd
    xlsx = tmp_path / "ok.xlsx"
    rows = [{"ASIN": f"B00{i}", "Brand": "X", "Price": 15.0 + i,
             "Ratings": 4.0, "Review Count": 10, "Creation date": "2024-01-01",
             "Unit Sales": 100, "Total Revenue": 1000, "时间": "2025-01"} for i in range(8)]
    pd.DataFrame(rows).to_excel(xlsx, index=False, engine="openpyxl")
    bands = recommend_bands(str(xlsx))
    assert len(bands) == 3
    assert all(isinstance(b, int) for b in bands)
    assert bands == sorted(bands)
