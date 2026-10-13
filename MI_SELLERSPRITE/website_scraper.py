#!/usr/bin/env python3
"""卖家精灵网站 API 抓取器（JWT/cookie 鉴权，oceanwing07 可用）。

走 www.sellersprite.com/v3/api/competing-lookup，**只按父 ASIN 维度**输出与扩展接口
同格式（下划线）的 List[dict]，可直接喂 sellersprite_to_mi.convert_data。

背景：扩展接口 e.sellersprite.com 对现有三账号全 ERR_GLOBAL_403；网站 API 对 07 可用。
真实月销量 = amzUnitTrends（驼峰）→ amz_unit_trends（下划线）；
trends 字段是 1.2×~5× 放大假数据，弃用。

**维度策略（固定父 ASIN）**：symbolFlag=False 抓父根+全部子变体，再按 parent 字段
归并成父 ASIN，月销量为变体组同月求和。symbolFlag=True 只抓主显示变体会漏掉兄弟
变体，实测低估 25~60%，故不采用。报告分析全程基于父 ASIN 维度。

JWT/cookie 有时效（~24h），过期需更新 cookie 文件（手动抓 curl 或后续自动登录）。
"""
import json
import re
import time
import urllib.parse
from collections import defaultdict
from pathlib import Path

import requests

API = "https://www.sellersprite.com/v3/api/competing-lookup"
# website_scraper.py 在 MI_SELLERSPRITE/，parents[1] = project 根
DEFAULT_COOKIE_FILE = (
    Path(__file__).resolve().parents[1] / ".superpowers" / "sdd" / "v3_cookie.txt"
)
PAGE_SIZE = 60
# 页间延时（秒）：competing-lookup 有严格滑动窗口限流（实测 ~10 req/min），
# 超速会被静默回空 (code:OK data:null)。7s/页留余量，稳态不触发限流。
PAGE_DELAY = 7.0

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
)


class SessionExpired(RuntimeError):
    """JWT/JSESSIONID 过期，需更新 cookie 文件。"""


def _load_cookie(cookie_file):
    p = Path(cookie_file)
    if not p.exists():
        raise SessionExpired(f"cookie 文件不存在: {p}")
    return p.read_text(encoding="utf-8").strip()


def _referer(body):
    """构造与请求 body 匹配的 competitor-lookup 页面 referer。

    服务端会校验 referer 的 query 状态（nodeIdPaths / market / order 等），
    裸 referer 会被静默回空（code:OK data:null）。page 固定为 1（浏览器翻页时
    referer 保持初始页面 URL，只有 body.page 变）。
    """
    node = (body.get("nodeIdPaths") or [""])[0]
    order = body.get("order") or {}
    q = urllib.parse.urlencode({
        "market": body.get("market", "US"),
        "monthName": body.get("monthName", "bsr_sales"),
        "asins": "[]",
        "page": "1",
        "nodeIdPaths": f'["{node}"]',
        "symbolFlag": str(body.get("symbolFlag", False)).lower(),
        "size": str(body.get("size", 60)),
        "order[field]": order.get("field", "total_units"),
        "order[desc]": "true",
        "lowPrice": body.get("lowPrice", "N"),
        "salesGrowthType": body.get("salesGrowthType", "30d"),
    })
    return "https://www.sellersprite.com/v3/competitor-lookup?" + q


def _headers(cookie, body=None):
    """完整浏览器风格 header。body 给定时构造匹配的 referer（必需）。"""
    m = re.search(r"Sprite-X-Token=([^;]+)", cookie)
    if not m:
        raise SessionExpired("cookie 中无 Sprite-X-Token（JWT）")
    return {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "content-type": "application/json;charset=UTF-8",
        "cookie": cookie,
        "origin": "https://www.sellersprite.com",
        "priority": "u=1, i",
        "referer": _referer(body) if body else "https://www.sellersprite.com/v3/competitor-lookup",
        "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": _UA,
        "Sprite-X-Token": m.group(1),
    }


def _group_by_parent(items: list) -> list:
    """按 parent ASIN 归并：每个变体组一行，月销量 = 组内所有 ASIN 同月求和。

    父根（变体容器，parent=self）本身无销量趋势；真实销量分散在各子变体，
    必须同月求和才是父维度真实销量（symbolFlag=True 只抓主变体会漏掉其余子变体，
    实测可低估 ~37%）。代表字段（brand/price/rating/reviews/available_days）
    取组内 symbol=Y 主显示变体；ASIN 标识用 parent（变体组根）。
    """
    from collections import defaultdict

    groups = defaultdict(list)
    for it in items:
        parent = it.get("parent") or it.get("asin")
        groups[parent].append(it)

    result = []
    for parent, members in groups.items():
        rep = next((m for m in members if m.get("symbol") == "Y"), members[0])
        sum_sales = defaultdict(int)
        for m in members:
            for t in (m.get("amzUnitTrends") or []):
                dk = t.get("dk")
                if dk:
                    sum_sales[dk] += int(t.get("sales", 0) or 0)
        result.append({
            "asin": parent,
            "brand": rep.get("brand"),
            "price": rep.get("price"),
            "rating": rep.get("rating"),
            "reviews": rep.get("reviews") or 0,
            "available_days": rep.get("availableDays"),
            "amz_unit_trends": [{"dk": dk, "sales": v} for dk, v in sorted(sum_sales.items())],
        })
    return result


def verify_parent_merge(raw_items, merged):
    """核对 _group_by_parent 归并完整性（四重守恒），返回 (ok, report_lines)。

    raw_items: 归并前的原始 API items（驼峰，含 parent / amzUnitTrends）。
    merged:    _group_by_parent 输出（下划线父维度 List[dict]）。

    四重守恒：
      1 数量守恒 — 每个 raw item 都进了某组（入组成员总和 == raw 总数）
      2 父键一致 — raw distinct(parent) 数 == merged 组数
      3 来源一致 — merged 每个父 ASIN 都能在 raw 分组键里找到（无幻觉）
      4 销量守恒 — 每个父组子成员 amzUnitTrends 同月求和 == merged 该月销量（全量逐月）
    """
    report = []
    ok = True

    # 用与 _group_by_parent 完全一致的键逻辑重算分组
    groups = defaultdict(list)
    for it in raw_items:
        p = it.get("parent") or it.get("asin")
        groups[p].append(it)

    n_raw = len(raw_items)
    n_grouped = sum(len(v) for v in groups.values())
    ok1 = n_raw == n_grouped
    report.append(f"[1 数量守恒] raw={n_raw}, 入组成员总和={n_grouped} → "
                  + ("✓" if ok1 else "✗ 有 raw item 被丢弃"))
    ok &= ok1

    n_distinct = len(groups)
    n_merged = len(merged)
    ok2 = n_distinct == n_merged
    report.append(f"[2 父键一致] raw distinct parent={n_distinct}, merged 组数={n_merged} → "
                  + ("✓" if ok2 else "✗ 组数不符（漏并/错并）"))
    ok &= ok2

    raw_keys = set(groups.keys())
    phantom = [m.get("asin") for m in merged if m.get("asin") not in raw_keys]
    ok3 = not phantom
    report.append("[3 来源一致] merged 父ASIN 是否都来自 raw 分组 → "
                  + ("✓" if ok3 else f"✗ {len(phantom)} 个孤立(无来源): {phantom[:5]}"))
    ok &= ok3

    merged_sales = {
        m.get("asin"): {str(t.get("dk")): int(t.get("sales", 0) or 0)
                        for t in (m.get("amz_unit_trends") or [])}
        for m in merged
    }
    checked = mismatch = 0
    samples = []
    for parent, members in groups.items():
        sum_dk = defaultdict(int)
        for m in members:
            for t in (m.get("amzUnitTrends") or []):
                dk = str(t.get("dk", ""))
                if dk:
                    sum_dk[dk] += int(t.get("sales", 0) or 0)
        target = merged_sales.get(parent, {})
        for dk, s in sum_dk.items():
            checked += 1
            if target.get(dk, 0) != s:
                mismatch += 1
                if len(samples) < 5:
                    samples.append(f"{parent}@{dk}: 子求和={s} merged={target.get(dk, 0)}")
    ok4 = mismatch == 0
    report.append(f"[4 销量守恒] 逐月核对 {checked} 个(父组×月)，不一致 {mismatch} → "
                  + ("✓" if ok4 else f"✗ 求和有误 {samples}"))
    ok &= ok4

    report.append("\n结论: " + ("✅ 归并完整，无丢项/错并/销量偏差"
                                if ok else "❌ 存在问题（见上）"))
    return ok, report


def _post_page(headers: dict, body: dict, throttle_retries: int = 4) -> dict:
    """单页 POST。网络/解析错误重试 3 次；data=null（限流软失败）按退避重试。

    返回解析后的 JSON dict。code 判定（含 SessionExpired）由调用方处理——
    本函数只关心"拿到真实响应"。限流特征：code:OK 但 data 整体为 null（真实
    空类目是 data:{total:0,items:[]}，data 仍是 dict），据此区分限流与真空。
    """
    def _once():
        last_err = None
        for net in range(3):  # 网络层重试
            try:
                return requests.post(API, headers=headers, json=body, timeout=30).json()
            except Exception as e:  # 网络错误 / JSON 解析失败
                last_err = e
                if net < 2:
                    time.sleep(1.0 * (net + 1))
        raise RuntimeError(f"分页请求失败（网络/解析，重试 3 次）: {last_err}")

    d = _once()
    # data=null 视为限流软失败，退避重试。窗口需要较长"安静期"才能清空，故退避
    # 拉长（重试请求本身也会计入窗口，间隔不够会反复触发）。
    backoff = (20, 40, 60, 60)
    for attempt in range(throttle_retries):
        if isinstance(d.get("data"), dict):
            return d
        wait = backoff[min(attempt, len(backoff) - 1)]
        print(f"[website_scraper] 第{body.get('page')}页 data=null 疑似限流，{wait}s 后重试 "
              f"({attempt + 1}/{throttle_retries})")
        time.sleep(wait)
        d = _once()
    return d  # 限流重试用尽，返回最后结果（data 仍可能为 null），调用方按 total/items 判定


def fetch_category(
    market: str,
    node_path: str,
    cookie_file=None,
    size: int = PAGE_SIZE,
    page_delay: float = PAGE_DELAY,
    max_pages: int = 200,
    month_name: str = "bsr_sales",
    dump_raw=None,
) -> list:
    """自动翻页拉满整个类目，按父 ASIN 维度归并后返回 MI 下划线格式的 List[dict]。

    翻页：page 从 1 递增，每页 size 条，直到 (a) 某页返回不满 size（已到尾）、
    (b) 累计达到 API 报告的 total、或 (c) 达到 max_pages 上限。每页打印进度；
    跨页按 ASIN 去重（防翻页重叠导致销量双计）；若累计 < total（API 截断大类目）
    或触顶 max_pages，打印警告。

    month_name（关键覆盖参数）：
      - 'bsr_sales'（默认）：完整类目（实测洗碗机 598 个商品），含全部品牌长尾。
        多数长尾新品无销量估算（trends 为空），但品牌/商品清单完整，不漏品牌。
      - 'bsr_sales_nearly'：仅"近期有销量活动"子集（同一类目仅 189 个），trends
        密度高，但会整品牌漏掉（AMANA/Bertazzoni/Cafe 等不在其中）。除非只关心
        近期活跃品，否则不要用。

    固定 symbolFlag=False（抓父根+全部子变体），再按 parent 字段归并成父 ASIN：
    每个变体组一行，月销量 = 组内所有 ASIN 同月求和（symbolFlag=True 只抓主变体
    会漏掉兄弟变体，实测低估 25~60%，故不采用）。

    Args:
        market: 站点代码（US/UK/DE/...）
        node_path: 类目节点路径，作 nodeIdPaths 的单元素。建议用网页能出数据的
                   完整三段冒号路径（如 '2619525011:3741271:3741281'）。
        cookie_file: cookie 文件路径（默认 .superpowers/sdd/v3_cookie.txt）
        max_pages: 翻页硬上限（默认 200 页 ≈ 12000 条，防失控）
        month_name: 销量数据集，默认 'bsr_sales'（完整类目）
    """
    cookie_file = cookie_file or DEFAULT_COOKIE_FILE
    cookie = _load_cookie(cookie_file)

    all_items = []
    seen = set()  # 跨页 ASIN 去重，防翻页重叠导致 _group_by_parent 销量双计
    total = 0
    page = 1
    while page <= max_pages:
        body = {
            "market": market,
            "monthName": month_name,
            "asins": [],
            "page": page,
            "nodeIdPaths": [node_path],
            "symbolFlag": False,
            "size": size,
            "order": {"field": "total_units", "desc": True},
            "lowPrice": "N",
            "salesGrowthType": "30d",
        }
        headers = _headers(cookie, body)  # referer 需逐请求匹配 body
        d = _post_page(headers, body)
        code = d.get("code")
        if code == "ERR_GLOBAL_SESSION_EXPIRED":
            raise SessionExpired("JWT/session 过期：请在浏览器打开 sellersprite.com 访问/重新登录触发续期，再重跑")
        if code != "OK":
            raise RuntimeError(f"API 返回错误: code={code} message={d.get('message')}")

        data = d.get("data")
        if not isinstance(data, dict):
            print(f"[website_scraper] 第{page}页: 无 data，结束翻页")
            break
        items = data.get("items") or []
        if data.get("total"):
            total = data["total"]

        # 跨页去重（保留首次出现）
        fresh = []
        for it in items:
            a = it.get("asin")
            if a and a in seen:
                continue
            if a:
                seen.add(a)
            fresh.append(it)
        all_items.extend(fresh)
        progress = f" / total {total}" if total else ""
        print(f"[website_scraper] 第{page}页: {len(items)} 条（去重新增 {len(fresh)}，累计 {len(all_items)}{progress}）")

        # 终止：本页空 / 不满（到尾）/ 累计达 total
        if not items or len(items) < size or (total and len(all_items) >= total):
            break
        page += 1
        if page_delay:
            time.sleep(page_delay)

    if total and len(all_items) < total:
        print(f"[website_scraper] ⚠️ 仅取到 {len(all_items)}/{total}，API 疑似截断大类目；"
              f"可按价位段（lowPrice/highPrice）拆分多次抓取以突破上限")
    if page >= max_pages and len(all_items) >= max_pages * size:
        print(f"[website_scraper] ⚠️ 触达 max_pages={max_pages} 上限，可能未抓完（如需更多请调大 max_pages）")

    if dump_raw:
        Path(dump_raw).write_text(json.dumps(all_items, ensure_ascii=False), encoding="utf-8")
        print(f"[website_scraper] 归并前原始 API items → {dump_raw}（{len(all_items)} 条，供 verify_parent_merge 核对）")
    out = _group_by_parent(all_items)
    print(f"[website_scraper] {market} / {node_path}: 共 {len(all_items)} 条 → 归并 {len(out)} 个父 ASIN（变体组合并）")
    return out


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(description="卖家精灵网站 API 抓取（07 JWT）")
    ap.add_argument("--market", default="US")
    ap.add_argument(
        "--node-path", required=True,
        help="类目节点路径，如 2619525011:3741271:3741281",
    )
    ap.add_argument("--cookie", default=str(DEFAULT_COOKIE_FILE))
    ap.add_argument("--out", default="", help="输出归并后 raw.json 路径（默认只打印统计）")
    ap.add_argument("--dump-raw", default="",
                    help="同时输出归并前原始 API items（供 verify_parent_merge 核对归并完整性）")
    a = ap.parse_args()

    data = fetch_category(a.market, a.node_path, a.cookie,
                          dump_raw=a.dump_raw or None)
    with_trend = sum(1 for e in data if e["amz_unit_trends"])
    print(f"共 {len(data)} 条，有 amz_unit_trends: {with_trend} 条")
    if a.out:
        Path(a.out).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        print(f"已写入 {a.out}")
    if a.dump_raw and a.out:
        raw_items = json.loads(Path(a.dump_raw).read_text(encoding="utf-8"))
        ok, report = verify_parent_merge(raw_items, data)
        print("\n".join(["", "=== 归并完整性核对 ==="] + report))
