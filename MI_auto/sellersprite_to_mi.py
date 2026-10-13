#!/usr/bin/env python3
"""卖家精灵 raw JSON → MI 合规长表 xlsx 转换器（不改 MI 任何脚本）。

对齐方案（已与 clean_data.py 字段逐一核对）：
  - ASIN/Brand/Price/Ratings/Review Count：ASIN 级标量，直接取
  - 时间：amz_unit_trends[].dk  '202406' → '2024-06'
  - Unit Sales：amz_unit_trends[].sales（真实月销量；trends 是放大假数据，弃用）
  - Total Revenue：price × 当月 sales（口径与销量自洽）
  - Creation date：采集日(2026-07-01) − available_days
"""
import json
import os
from datetime import date, timedelta

import pandas as pd

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(_PROJECT_ROOT, "MI_SELLERSPRITE", "output", "sports_water_bottles_raw.json")
OUT_DIR = os.path.join(_PROJECT_ROOT, "MI_auto", "MI", "data")
OUT = os.path.join(OUT_DIR, "sports_water_bottles.xlsx")
CRAWL = date(2026, 7, 1)  # 采集日锚点（数据最晚月 202606/202607 推断，已与用户确认）


def convert_data(data, crawl, include_no_trends=True):
    """卖家精灵 data(List[dict]) → MI 9 字段长表 DataFrame。

    - 时间：amz_unit_trends[].dk '202406' → '2024-06'
    - Unit Sales：amz_unit_trends[].sales（真实月销量）
    - Total Revenue：price × sales
    - Creation date：crawl − available_days

    include_no_trends=True 时，对 amz_unit_trends 为空的产品（卖家精灵无销量估算，
    多为新品/长尾）补一行零销量占位行，挂在数据最新月份。这样它们会进入报告的
    价格分布(Module4)、新品计数(Module5)、品牌 ASIN 数(Module2)等【计数】指标，
    而收入/销量求和只加 0、不影响任何金额指标；效率模块(Module6)靠"销量>中位数"
    过滤自动排除它们。挂到最新月保证落在 last_12 窗口内被计入。
    """
    from datetime import timedelta
    rows = []

    # 先扫出数据里最新的月份，作为无 trends 占位行的 时间 锚点
    latest_ym = None
    if include_no_trends:
        all_dks = [
            it.get("dk", "")
            for e in data
            for it in (e.get("amz_unit_trends") or [])
            if len(str(it.get("dk", ""))) == 6
        ]
        if all_dks:
            latest_dk = max(all_dks)
            latest_ym = f"{latest_dk[:4]}-{latest_dk[4:]}"
        else:
            latest_ym = crawl.strftime("%Y-%m")  # 全无 trends 时退回采集月

    for e in data:
        asin = e["asin"]
        brand = e.get("brand") or "Unknown"
        price = e.get("price")
        rating = e.get("rating")
        reviews = e.get("reviews", 0) or 0
        ad = e.get("available_days")
        creation = (crawl - timedelta(days=ad)).isoformat() if ad else None
        trends = e.get("amz_unit_trends") or []
        for it in trends:
            dk = it.get("dk", "")
            if len(dk) != 6:
                continue
            ym = f"{dk[:4]}-{dk[4:]}"
            sales = it.get("sales", 0) or 0
            revenue = (price * sales) if price else 0
            rows.append({
                "ASIN": asin, "Brand": brand, "Price": price,
                "Ratings": rating, "Review Count": reviews,
                "Creation date": creation, "Unit Sales": sales,
                "Total Revenue": revenue, "时间": ym,
            })
        # 无销量估算产品补一行零销量占位，使其进入计数/价格分布
        if include_no_trends and not trends:
            rows.append({
                "ASIN": asin, "Brand": brand, "Price": price,
                "Ratings": rating, "Review Count": reviews,
                "Creation date": creation, "Unit Sales": 0,
                "Total Revenue": 0, "时间": latest_ym,
            })
    return pd.DataFrame(rows)


def raw_to_xlsx(data, xlsx_path):
    """raw.json（父 ASIN 维度归并后的下划线格式）→ 两 sheet Excel，便于人工核对抓取完整性。

    Sheet1「父ASIN汇总」：每个父 ASIN 一行，含品牌/价格/评分/上架天数 + 趋势月数、
        24 月总销量、最新月份及销量、是否有销量数据。一眼看出共抓多少品、覆盖率、
        漏没漏品牌（可按 Brand 排序/筛选）。
    Sheet2「月度销量明细」：ASIN×月 长表，仅真实抓到的 amz_unit_trends（不补零），
        供逐月核验销量数字。
    """
    summary, detail = [], []
    for e in data:
        trends = e.get("amz_unit_trends") or []
        sales_by_dk = {str(t.get("dk", "")): (t.get("sales", 0) or 0) for t in trends}
        dks = sorted(d for d in sales_by_dk if len(d) == 6)
        summary.append({
            "ASIN": e.get("asin"),
            "Brand": e.get("brand"),
            "Price": e.get("price"),
            "Rating": e.get("rating"),
            "Reviews": e.get("reviews"),
            "AvailableDays": e.get("available_days"),
            "TrendMonths": len(dks),
            "TotalUnits24m": sum(sales_by_dk[d] for d in dks),
            "FirstDK": dks[0] if dks else "",
            "LatestDK": dks[-1] if dks else "",
            "LatestMonthSales": sales_by_dk[dks[-1]] if dks else "",
            "HasSales": "Y" if dks else "N",
        })
        for dk in dks:
            detail.append({
                "ASIN": e.get("asin"),
                "Brand": e.get("brand"),
                "DK": dk,
                "Year-Month": f"{dk[:4]}-{dk[4:]}",
                "Sales": sales_by_dk[dk],
            })
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as xw:
        pd.DataFrame(summary).to_excel(xw, sheet_name="父ASIN汇总", index=False)
        pd.DataFrame(detail).to_excel(xw, sheet_name="月度销量明细", index=False)
    return len(summary), len(detail)


def main():
    data = json.load(open(RAW, encoding="utf-8"))
    df = convert_data(data, CRAWL)
    os.makedirs(OUT_DIR, exist_ok=True)
    df.to_excel(OUT, index=False, engine="openpyxl")
    print(f"✓ 已生成: {OUT}")
    print(f"  行数(ASIN×月): {len(df)}  ASIN 数: {df['ASIN'].nunique()}")
    print(f"  时间范围: {df['时间'].min()} ~ {df['时间'].max()}")


if __name__ == "__main__":
    main()
