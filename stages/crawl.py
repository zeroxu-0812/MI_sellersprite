"""阶段 ① 采集：交互选站点 + 搜品类 → 翻页抓父ASIN → raw.json/raw.xlsx/crawl_meta.json。"""
import base64
import json
import time

from website_scraper import (
    fetch_category, SessionExpired, _load_cookie, _headers,
    DEFAULT_COOKIE_FILE, verify_parent_merge,
)
from refresh_cookie import refresh
from verify_coverage import _query_total
from sellersprite_to_mi import raw_to_xlsx
from run_dir import new_run_dir, RunPaths
import category_search

MARKETS = {
    "US": "$", "UK": "£", "DE": "€", "FR": "€", "IT": "€", "ES": "€",
    "CA": "C$", "JP": "¥", "IN": "₹", "MX": "Mex$",
}


def _jwt_exp(token):
    try:
        payload = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "==")).get("exp")
    except Exception:
        return None


def ensure_cookie_fresh(cookie_file=None):
    """JWT exp 已过 → 从浏览器刷新一次（软过期会让 competing-lookup 静默回空）。"""
    cookie_file = cookie_file or str(DEFAULT_COOKIE_FILE)
    try:
        cookie = _load_cookie(cookie_file)
    except SessionExpired:
        cookie = ""
    m = cookie and cookie.split("Sprite-X-Token=")
    token = m[1].split(";")[0] if m and len(m) > 1 else ""
    exp = _jwt_exp(token) if token else None
    if not exp or exp <= int(time.time()):
        print("[crawl] cookie 过期或临期，从浏览器刷新...")
        refresh(cookie_file=cookie_file)


def probe_total(market, node_path, cookie_file=None):
    """size=1 探测类目总量（失败返 None）。"""
    try:
        headers = _headers(_load_cookie(cookie_file or str(DEFAULT_COOKIE_FILE)))
        return _query_total(headers, market, node_path, "bsr_sales")
    except Exception as e:
        print(f"[crawl] 预估总量失败（忽略）: {e}")
        return None


def _fetch_with_refresh(market, node_path, cookie_file=None, dump_raw=None):
    """fetch_category，遇 SessionExpired 自动刷新重试一次。dump_raw 透传给 fetch_category。"""
    try:
        return fetch_category(market, node_path, cookie_file=cookie_file, dump_raw=dump_raw)
    except SessionExpired:
        print("[crawl] 抓取中 session 过期，刷新重试...")
        try:
            refresh(cookie_file=cookie_file or str(DEFAULT_COOKIE_FILE))
        except Exception as e:
            raise RuntimeError(
                f"刷新 cookie 失败: {e}（请在浏览器登录 sellersprite.com 后重跑）"
            )
        return fetch_category(market, node_path, cookie_file=cookie_file, dump_raw=dump_raw)


def run(market=None, cat_label=None, node_path=None, run_dir=None, interactive=True) -> RunPaths:
    if interactive:
        market = market or prompt_market()
        if not node_path:
            cat_label, node_path = prompt_category(market)
        cat_label = cat_label or node_path

    ensure_cookie_fresh()
    paths = run_dir or new_run_dir(market, cat_label or "category")

    total = probe_total(market, node_path)
    print(f"[crawl] {market} / {node_path}（预估 {total if total else '未知'} 条），开始翻页...")
    raw_dump = paths.root / "_raw_items_dump.json"
    data = _fetch_with_refresh(market, node_path, dump_raw=str(raw_dump))
    if not data:
        raise RuntimeError(f"抓取无数据：market={market} node={node_path}")

    # 归并完整性自检：fetch_category 已把归并前 raw items dump 到 raw_dump
    verify_ok = None
    if raw_dump.exists():
        try:
            raw_items = json.loads(raw_dump.read_text(encoding="utf-8"))
            ok, lines = verify_parent_merge(raw_items, data)
            print("\n".join(["", "=== 归并完整性自检 ==="] + lines))
            verify_ok = ok
        except Exception as e:
            print(f"[crawl] 自检异常(忽略): {e}")
    raw_dump.unlink(missing_ok=True)

    paths.raw_json.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    n_parent, n_detail = raw_to_xlsx(data, str(paths.raw_xlsx))
    meta = {
        "market": market, "category": cat_label, "node_path": node_path,
        "total_probed": total, "parent_asins": len(data), "raw_xlsx_detail_rows": n_detail,
        "verify_parent_merge": verify_ok,
    }
    paths.crawl_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[crawl] ✅ {len(data)} 父ASIN → {paths.raw_json}")
    return paths


# ── 交互提示（仅 interactive=True 时用）──────────────────────

def prompt_market() -> str:
    items = list(MARKETS.items())
    print("\n[选站点]")
    for i, (code, cur) in enumerate(items, 1):
        print(f"  {i}) {code} {cur}", end="   ")
        if i % 5 == 0:
            print()
    print()
    while True:
        s = input(f"选(1-{len(items)}): ").strip()
        if s.isdigit() and 1 <= int(s) <= len(items):
            return items[int(s) - 1][0]
        print("无效输入，重来")


def prompt_category(market) -> tuple:
    """交互选品类：默认逐级浏览品类树（下钻），browse 内含关键词搜(s)与手动(m)。

    浏览树用 US 站(marketId=1)结构作全局索引——品类层级全球一致，非 US 站点个别
    节点号可能略有差异；market != US 时给一句提示。
    """
    if market != "US":
        print("[选品类] 浏览树按 US 站结构（品类层级全球一致，非 US 站点个别节点号可能不同）")
    res = category_search.browse()
    if res:
        return res
    print("浏览取消，回退手动填路径。")
    return _prompt_manual_path()


def _prompt_manual_path() -> tuple:
    node = input("输入 node 路径（如 2619525011:3741271:3741281）: ").strip()
    label = input("类目名(可选，回车用 node): ").strip() or node
    return label, node
