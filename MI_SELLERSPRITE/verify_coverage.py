#!/usr/bin/env python3
"""Layer 4 数据源完整性交叉校验：验证 API 报告的 total 是不是类目真实全量。

核心思路——分区求和守恒：把类目按价格或品牌切成若干**不重叠**分区，各分区独立查
total 再求和。若求和 == overall total，说明 overall 没被 API 截断（是真全量）；
若求和 > overall，说明 overall 被截断（真全量更大，需按分区抓）。

两种独立分区法（互相印证）：
  --price-partition  价位分区（推荐，请求少）：disjoint price bands 各自查 total
  --brands-from FILE 品牌分区：从抓取结果取品牌清单，内部求和 + 可选 API 抽查

用法：
  # 价位分区（4 个请求）+ 用已有抓取数据做品牌内部求和
  python verify_coverage.py --market US --node-path 2619525011:3741271:3741281 \
      --price-bands "[0,100,300,600]" --brands-from output/ss_bsr_full.json

  # 额外抽查 5 个品牌（每个 1 请求），核对 API 品牌数 == 我们抓到的数
  python verify_coverage.py ... --spot-check-brands 5

判读：
  overall = T
  price 求和 = Sp,  brand 求和 = Sb
  - Sp == T 且 Sb == T  → ✅ total 是真全量，无截断
  - Sp > T 或 Sb > T    → ⚠️ overall 被截断，真全量 = max(Sp, Sb)，需分区抓
  - Sp < T              → 价位带漏了 null 价格品（不代表截断；看品牌求和）
"""
import argparse
import json
from collections import Counter

import requests

import website_scraper as ws


def _query_total(headers, market, node_path, month_name, **body_over):
    """单次查询返回 total；session 过期抛 SessionExpired。

    referer 必须匹配 body（服务端校验 query 状态），故用 body 覆盖 referer；
    走 ws._post_page 复用限流退避重试。
    """
    body = {
        "market": market,
        "monthName": month_name,
        "asins": [],
        "page": 1,
        "nodeIdPaths": [node_path],
        "symbolFlag": False,
        "size": 1,
        "order": {"field": "total_units", "desc": True},
        "lowPrice": "N",
        "salesGrowthType": "30d",
    }
    body.update(body_over)
    h = dict(headers)
    h["referer"] = ws._referer(body)
    d = ws._post_page(h, body)
    code = d.get("code")
    if code == "ERR_GLOBAL_SESSION_EXPIRED":
        raise ws.SessionExpired("JWT/session 过期：请在浏览器打开 sellersprite.com 触发续期后重跑（或先跑 refresh_cookie.py）")
    if code != "OK":
        raise RuntimeError(f"API 错误 code={code} message={d.get('message')}")
    data = d.get("data")
    return data.get("total") if isinstance(data, dict) else 0


def price_partition(headers, market, node_path, month_name, bands):
    """价位分区：bands=[b0,b1,...,bN] → 带 [b0-b1, b1-b2, ..., bN-+∞]，各查 total 求和。"""
    print(f"\n[价位分区] bands={bands}")
    parts = []
    for i in range(len(bands)):
        low = bands[i]
        high = bands[i + 1] if i + 1 < len(bands) else None
        over = {"lowPrice": low}
        if high is not None:
            over["highPrice"] = high
        t = _query_total(headers, market, node_path, month_name, **over)
        label = f"${low}-{high}" if high is not None else f"${low}+"
        parts.append((label, t))
        print(f"  {label:>14}: {t}")
    s = sum(t for _, t in parts)
    print(f"  {'求和':>14}: {s}")
    return s


def brand_internal_sum(brands_file):
    """从抓取结果（父维度 raw.json）算品牌→ASIN 数，求和。0 个 API 请求。

    验证：每个抓到的品都有品牌、求和是否 == 抓取条数（内部一致性）。
    """
    data = json.loads(open(brands_file, encoding="utf-8").read())
    counts = Counter((e.get("brand") or "(无品牌)") for e in data)
    print(f"\n[品牌内部求和] 来源 {brands_file}（{len(data)} 条父ASIN）")
    print(f"  品牌数: {len(counts)}, 求和: {sum(counts.values())}")
    print(f"  top5: {counts.most_common(5)}")
    return sum(counts.values()), counts


def brand_spot_check(headers, market, node_path, month_name, counts, n):
    """抽查 n 个品牌的 API total，对比我们抓到的数。每品牌 1 请求。"""
    print(f"\n[品牌 API 抽查] top {n}")
    for brand, scraped_n in counts.most_common(n):
        t = _query_total(headers, market, node_path, month_name, brand=brand)
        match = "✓" if t == scraped_n else "✗"
        print(f"  {match} {brand}: API={t} 抓取={scraped_n}")


def main():
    ap = argparse.ArgumentParser(description="Layer 4 数据源完整性交叉校验")
    ap.add_argument("--market", default="US")
    ap.add_argument("--node-path", required=True)
    ap.add_argument("--cookie", default=str(ws.DEFAULT_COOKIE_FILE))
    ap.add_argument("--month-name", default="bsr_sales")
    ap.add_argument("--price-bands", default="[0,100,300,600]",
                    help='价位分区边界 JSON，如 "[0,100,300,600]" → 4 带')
    ap.add_argument("--brands-from", default="",
                    help="抓取结果 raw.json 路径，做品牌内部求和（0 请求）")
    ap.add_argument("--spot-check-brands", type=int, default=0,
                    help="额外抽查 N 个品牌 via API（每品牌 1 请求）")
    args = ap.parse_args()

    headers = ws._headers(ws._load_cookie(args.cookie))

    overall = _query_total(headers, args.market, args.node_path, args.month_name)
    print(f"=== Layer 4 数据源完整性交叉校验 ===")
    print(f"overall total = {overall}  ({args.market} / {args.node_path} / {args.month_name})")

    results = {"overall": overall}

    # 价位分区
    bands = json.loads(args.price_bands)
    results["price_sum"] = price_partition(headers, args.market, args.node_path,
                                           args.month_name, bands)

    # 品牌内部求和
    if args.brands_from:
        s, counts = brand_internal_sum(args.brands_from)
        results["brand_sum"] = s
        if args.spot_check_brands > 0:
            brand_spot_check(headers, args.market, args.node_path, args.month_name,
                             counts, args.spot_check_brands)

    # 判读
    print(f"\n=== 判读 ===")
    T = overall
    verdicts = []
    if "price_sum" in results:
        sp = results["price_sum"]
        verdicts.append(f"价位求和 {sp} vs overall {T}: "
                        + ("✅一致" if sp == T else ("⚠️大于→overall 被截断" if sp > T else "小于→可能 null 价格品未入带")))
    if "brand_sum" in results:
        sb = results["brand_sum"]
        verdicts.append(f"品牌求和 {sb} vs overall {T}: "
                        + ("✅一致" if sb == T else ("⚠️大于→overall 被截断" if sb > T else "小于→有品牌未抓到/无品牌品")))
    print("\n".join(verdicts))
    print(f"\n结论: " + ("✅ total 是真全量，无截断" if any("✅" in v for v in verdicts)
          else "⚠️ overall 疑似截断或漏项，见上方分项"))


if __name__ == "__main__":
    main()
