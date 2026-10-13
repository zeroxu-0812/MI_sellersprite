#!/usr/bin/env python3
"""统一市场洞察管线 orchestrator：站点+类目 → 抓取 → 转换 → MI 报告。"""
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "MI_auto"))
sys.path.insert(0, str(PROJECT_ROOT / "MI_SELLERSPRITE"))

from sellersprite_to_mi import convert_data, raw_to_xlsx  # noqa: E402


class CategoryNotFound(Exception):
    """类目名在字典中找不到唯一匹配。"""


def _load_categories(dict_path: str) -> dict:
    with open(dict_path, encoding="utf-8") as f:
        return json.load(f)


def resolve_category(name: str, dict_path: str = "categories.json") -> str:
    """类目名 → node ID。优先级：精确 key > alias > 模糊唯一匹配。"""
    cats = _load_categories(dict_path)
    key = name.lower().strip()

    # 1) 精确 key
    if key in cats:
        return cats[key]["id"]
    # 2) alias
    for k, info in cats.items():
        if key in [a.lower() for a in info.get("aliases", [])]:
            return info["id"]
    # 3) 模糊：key 包含于 类目名 或 alias
    fuzzy = [k for k, info in cats.items()
             if key in k.lower()
             or any(key in a.lower() for a in info.get("aliases", []))]
    if len(fuzzy) == 1:
        return cats[fuzzy[0]]["id"]
    if len(fuzzy) > 1:
        raise CategoryNotFound(f"类目「{name}」匹配多条：{fuzzy}，请用 --category-id 指定")
    raise CategoryNotFound(f"类目「{name}」未在字典中找到，用 --list-categories 查看，或 --category-id 直接传 ID")


def list_categories(keyword: str, dict_path: str = "categories.json") -> list:
    """按关键词模糊列出候选类目（名+ID+aliases）。空关键词返回全部。"""
    cats = _load_categories(dict_path)
    kw = keyword.lower().strip()
    rows = []
    for k, info in cats.items():
        if not kw or kw in k.lower() or any(kw in a.lower() for a in info.get("aliases", [])):
            rows.append({"name": k, "id": info["id"], "aliases": info.get("aliases", [])})
    return rows


CURRENCY_MAP = {
    "US": "$", "UK": "£", "DE": "€", "FR": "€", "IT": "€", "ES": "€",
    "CA": "C$", "JP": "¥", "IN": "₹", "MX": "Mex$",
}


def currency_for(market: str) -> str:
    return CURRENCY_MAP.get(market.upper().strip(), "$")


def _valid_dk(dk: str) -> bool:
    """dk 必须是 6 位数字，且表示合法年月（1<=月份<=12）。"""
    if not (len(dk) == 6 and dk.isdigit()):
        return False
    m = int(dk[4:])
    return 1 <= m <= 12


def infer_crawl_date(data: list) -> date:
    """取 data 中 amz_unit_trends 最晚月的次月初，作为采集日锚点。

    对每个 dk 做严格校验：必须 6 位数字且月份合法（1-12），
    非法值（如 '202613'、'2026ab'）直接跳过；全部非法则回退 date.today()。
    """
    max_dk = "0"
    for e in data:
        for it in e.get("amz_unit_trends", []) or []:
            dk = str(it.get("dk", ""))
            if _valid_dk(dk) and dk > max_dk:
                max_dk = dk
    if max_dk == "0":
        return date.today()
    y, m = int(max_dk[:4]), int(max_dk[4:])
    # 保险：max_dk 已过 _valid_dk，此处 m 必然 1-12
    if not (1 <= m <= 12):
        return date.today()
    if m == 12:
        return date(y + 1, 1, 1)
    return date(y, m + 1, 1)


def recommend_bands(xlsx_path: str) -> list:
    """按价格四分位（Q1/Q2/Q3，取整）推荐价位段切点。价格全空/NaN 时回退默认 [10,20,30]。"""
    df = pd.read_excel(xlsx_path)
    if df.empty or "Price" not in df.columns:
        return [10, 20, 30]
    pa = df.drop_duplicates("ASIN")["Price"].dropna()
    if pa.empty:
        return [10, 20, 30]
    q1, q2, q3 = pa.quantile([0.25, 0.5, 0.75])
    if pd.isna(q1) or pd.isna(q2) or pd.isna(q3):
        return [10, 20, 30]
    return [int(round(q1)), int(round(q2)), int(round(q3))]


def to_mi_long_table(data: list) -> "pd.DataFrame":
    """抓取 data → MI 长表（自动推断采集日）。"""
    crawl = infer_crawl_date(data)
    return convert_data(data, crawl)


MI_RUN = PROJECT_ROOT / "MI_auto" / "MI" / "run.py"


def run_mi(xlsx_path, currency, purpose, bands, fmt, out_dir):
    """子进程调 MI/run.py 生成报告。module5 崩溃时 run.py 非零退出 → 返回 None（保留已生成产物）。"""
    out_dir = str(out_dir)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, str(MI_RUN),
        "--data", str(xlsx_path),
        "--price-bands", json.dumps(bands),
        "--purpose", purpose,
        "--currency", currency,
        "--format", fmt,
        "--output", out_dir,
    ]
    print(f"[run_all] 调用 MI: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"[run_all] ⚠️ MI 非零退出({result.returncode})，通常因 module5 新品饼图数据为空。已生成产物保留在 {out_dir}")
        return None
    reports = sorted(Path(out_dir).glob("report_*.html"))
    return reports[-1] if reports else None


def fetch_raw(market: str, cat_id: str) -> list:
    """抓取类目父 ASIN 趋势数据（网站 API competing-lookup，cookie/JWT 鉴权）。

    cat_id 作 nodeIdPaths 元素，建议传完整路径（如 2619525011:3741271:3741281）。
    cookie 过期时自动从浏览器刷新后重试一次。
    """
    from website_scraper import fetch_category, SessionExpired
    try:
        data = fetch_category(market, cat_id)
    except SessionExpired:
        # cookie 过期 → 从浏览器自动刷新后重试一次
        print("[run_all] cookie 过期，尝试从浏览器自动刷新...")
        try:
            from refresh_cookie import refresh
            refresh()
        except Exception as e:
            raise RuntimeError(
                f"自动刷新 cookie 失败: {e}（请在浏览器登录 sellersprite.com 后重跑）"
            )
        try:
            data = fetch_category(market, cat_id)
        except SessionExpired as e:
            raise RuntimeError(
                f"刷新后仍过期: {e}（浏览器会话也失效，手动登录 sellersprite 再跑）"
            )
    if not data:
        raise RuntimeError(f"抓取无数据：market={market} cat_id={cat_id}")
    print(f"[run_all] 抓取完成：{len(data)} 条")
    return data


def parse_args(argv=None):
    import argparse
    p = argparse.ArgumentParser(
        description="统一市场洞察管线：站点+类目 → 抓取 → 转换 → MI 报告")
    p.add_argument("--market", default="US",
                   choices=["US", "UK", "DE", "FR", "IT", "ES", "CA", "JP", "IN", "MX"],
                   help="站点代码（默认 US）")
    p.add_argument("--category", default="", help="类目名（查 categories.json）")
    p.add_argument("--category-id", default="", help="直接传类目 node ID（跳过字典）")
    p.add_argument("--list-categories", default=None, metavar="KEYWORD",
                   help="列出类目字典中匹配关键词的条目后退出")
    p.add_argument("--input", default="",
                   help="离线旁路：直接传卖家精灵 raw.json，跳过抓取")
    p.add_argument("--purpose", default="整体市场调研")
    p.add_argument("--price-bands", default="", help='JSON 数组如 "[15,20,25]"，不传则自动推荐')
    p.add_argument("--currency", default="", help="货币符号（默认按站点映射）")
    p.add_argument("--format", default="html", choices=["html", "pdf", "ppt", "all"])
    p.add_argument("--output", default=str(PROJECT_ROOT / "output"))
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    # --list-categories 模式
    if args.list_categories is not None:
        for r in list_categories(args.list_categories):
            print(f"{r['id']}\t{r['name']}\t{','.join(r['aliases'])}")
        return 0

    currency = args.currency.strip() or currency_for(args.market)

    # 决定数据来源：--input 旁路 vs 抓取
    if args.input:
        import json as _json
        data = _json.load(open(args.input, encoding="utf-8"))
        cat_label = Path(args.input).stem
    else:
        # 解析类目
        if args.category_id:
            cat_id = args.category_id.strip()
        elif args.category:
            try:
                cat_id = resolve_category(args.category)
            except CategoryNotFound as e:
                print(f"[ERROR] {e}")
                return 2
        else:
            print("[ERROR] 必须提供 --category 或 --category-id（或 --input 离线）")
            return 2
        cat_label = args.category.strip() or cat_id
        try:
            data = fetch_raw(args.market, cat_id)
        except RuntimeError as e:
            print(f"[ERROR] 抓取失败: {e}")
            return 3

    # 运行目录
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_cat = "".join(c if c.isalnum() else "-" for c in cat_label)[:40]
    run_dir = Path(args.output) / f"{args.market}_{safe_cat}_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)

    # 转换
    df = to_mi_long_table(data)
    if df.empty:
        print("[ERROR] 转换后 0 行数据（无有效 amz_unit_trends），无法分析")
        return 5
    input_xlsx = run_dir / "input.xlsx"
    df.to_excel(input_xlsx, index=False, engine="openpyxl")
    (run_dir / "raw.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")
    raw_xlsx = run_dir / "raw.xlsx"
    n_parent, n_detail = raw_to_xlsx(data, str(raw_xlsx))
    print(f"[run_all] 原始核对表 → {raw_xlsx}（{n_parent} 父ASIN / {n_detail} 月度明细行）")
    print(f"[run_all] 长表 {len(df)} 行 → {input_xlsx}")

    # price-bands
    if args.price_bands.strip():
        bands = json.loads(args.price_bands)
    else:
        bands = recommend_bands(str(input_xlsx))
    print(f"[run_all] price-bands = {bands}")

    # MI 报告
    report = run_mi(str(input_xlsx), currency, args.purpose,
                    bands, args.format, str(run_dir))

    # 汇总
    print("\n" + "=" * 60)
    print(f"✅ 运行目录: {run_dir}")
    if report:
        print(f"✅ 报告: {report}")
    else:
        print("⚠️ 报告未完整生成（可能 module5 新品为空），清洗/图表产物见运行目录")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
