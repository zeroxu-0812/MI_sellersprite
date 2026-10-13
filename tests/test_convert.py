import json
from datetime import date
import pandas as pd
from sellersprite_to_mi import convert_data

REQUIRED_COLS = ["ASIN", "Brand", "Price", "Ratings", "Review Count",
                 "Creation date", "Unit Sales", "Total Revenue", "时间"]


def test_convert_data_shape(raw_json_path):
    data = json.load(open(raw_json_path, encoding="utf-8"))
    crawl = date(2026, 7, 1)
    df = convert_data(data, crawl)
    assert list(df.columns) == REQUIRED_COLS
    assert df["ASIN"].nunique() == 30          # 30 个父 ASIN
    assert len(df) > 600                        # ASIN×月 长表
    assert df["时间"].min() >= "2023-08"        # amz 最早期
    assert df["时间"].max() <= "2026-06"


def test_convert_data_revenue_formula(raw_json_path):
    data = json.load(open(raw_json_path, encoding="utf-8"))
    df = convert_data(data, date(2026, 7, 1))
    # Total Revenue 应 ≈ Price × Unit Sales（每行）
    chk = (df["Price"] * df["Unit Sales"]).round(2)
    assert (chk == df["Total Revenue"].round(2)).all()


def test_convert_data_creation_backcalc(raw_json_path):
    data = json.load(open(raw_json_path, encoding="utf-8"))
    df = convert_data(data, date(2026, 7, 1))
    # 反推 Creation：2026-07-01 − available_days，最晚应 2025-06（available_days=387）
    asin0 = data[0]
    ad = asin0["available_days"]
    expected_dt = date(2026, 7, 1) - pd.Timedelta(days=ad)
    # date - Timedelta 可能返回 date 或 Timestamp，统一取 ISO 日期串
    expected = expected_dt.strftime("%Y-%m-%d") if hasattr(expected_dt, "strftime") else str(expected_dt)
    first = df[df["ASIN"] == asin0["asin"]]["Creation date"].iloc[0]
    assert first == expected


def test_to_mi_long_table_end_to_end(raw_json_path):
    import json
    from run_all import to_mi_long_table
    data = json.load(open(raw_json_path, encoding="utf-8"))
    df = to_mi_long_table(data)
    assert df["ASIN"].nunique() == 30
    assert "Total Revenue" in df.columns
    # 采集日应来自 data（最晚 202606 → 2026-07-01）
    asin0 = data[0]
    import pandas as pd
    from datetime import date
    expected_creation = str(date(2026, 7, 1) - pd.Timedelta(days=asin0["available_days"]))
    assert (df[df["ASIN"] == asin0["asin"]]["Creation date"] == expected_creation).all()
