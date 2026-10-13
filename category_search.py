"""类目关键词搜索：拉卖家精灵类目树缓存到本地，本地过滤。

机制（spike 实测）：GET /v2/competitor-lookup/nodes，cookie 鉴权；
nodeLabelPath=<根ID>（不带 table）返回该根整棵子树扁平列表。
无服务端 keyword 参数 → 全树缓存 + 本地过滤。
"""
import json
from pathlib import Path

import requests

import website_scraper as ws

NODES_URL = "https://www.sellersprite.com/v2/competitor-lookup/nodes"
CACHE_FILE = Path(__file__).resolve().parent / "categories_cache.json"
TREE_MARKET_ID = "1"  # US 树作全局 browse-tree 索引（结构跨站一致）


def _get_nodes(headers, params):
    r = requests.get(NODES_URL, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    d = r.json()
    if d.get("code") == "ERR_GLOBAL_SESSION_EXPIRED":
        raise ws.SessionExpired("nodes 接口 session 过期，刷新 cookie 后重试")
    return d.get("items") or []


def fetch_tree(cookie_file=None, market_id=TREE_MARKET_ID):
    """拉全类目树（25 根 + 各根子树），扁平去重返回。"""
    headers = ws._headers(ws._load_cookie(cookie_file or ws.DEFAULT_COOKIE_FILE))
    roots = _get_nodes(headers, {"marketId": market_id})
    tree = list(roots)
    for root in roots:
        rid = str(root.get("id")).split(":")[0]
        tree.extend(_get_nodes(headers, {"marketId": market_id, "nodeLabelPath": rid}))
    seen, uniq = set(), []
    for it in tree:
        iid = it.get("id")
        if iid and iid not in seen:
            seen.add(iid)
            uniq.append(it)
    return uniq


def save_tree(tree, path=CACHE_FILE):
    Path(path).write_text(json.dumps(tree, ensure_ascii=False), encoding="utf-8")


def load_tree(path=CACHE_FILE):
    p = Path(path)
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def search(keyword, tree=None, cookie_file=None, limit=30):
    """关键词搜类目，命中 label / 中文名 / 中文路径 / ID，按商品数降序。"""
    kw = (keyword or "").strip().lower()
    if not kw:
        return []
    tree = tree if tree is not None else (load_tree() or fetch_tree(cookie_file))
    hits = []
    for it in tree:
        label = it.get("label") or ""
        locale = it.get("nodeLabelLocale") or ""
        path_locale = it.get("nodeLabelPathLocale") or ""
        iid = str(it.get("id") or "")
        if kw in f"{label} {locale} {path_locale} {iid}".lower():
            hits.append({
                "name": (label.split(":")[-1] if label else locale),
                "node_path": iid,
                "product_count": it.get("products", 0),
                "locale_path": path_locale or locale,
            })
    hits.sort(key=lambda h: h["product_count"], reverse=True)
    return hits[:limit]


# ── 品类树逐级浏览（下钻）──────────────────────────────────────
# 扁平缓存里每个节点的 id 是冒号路径（如 2619525011:3741271:3741281），
# 层级就编码在里面：单段=根(25 个顶层类目)，每多一段深一级。据此重建树。

def build_index(tree=None, cookie_file=None):
    """从扁平缓存建浏览索引。

    返回 {by_id, children_map, roots}：
      - by_id: {id: node}
      - children_map: {父id: [直接子节点]}，子列表按 products 降序
      - roots: 顶层类目（id 单段），按 products 降序
    """
    tree = tree if tree is not None else (load_tree() or fetch_tree(cookie_file))
    by_id, children_map = {}, {}
    for it in tree:
        iid = str(it.get("id", ""))
        if not iid:
            continue
        by_id[iid] = it
        parts = iid.split(":")
        if len(parts) > 1:
            children_map.setdefault(":".join(parts[:-1]), []).append(it)
    for k in children_map:
        children_map[k].sort(key=lambda x: (x.get("products") or 0), reverse=True)
    roots = sorted(
        [it for it in tree if len(str(it.get("id", "")).split(":")) == 1],
        key=lambda x: (x.get("products") or 0), reverse=True,
    )
    return {"by_id": by_id, "children_map": children_map, "roots": roots}


def children_of(index, node_id):
    """node_id 的直接子节点列表（已按商品数降序）。根层用 index["roots"]。"""
    return index["children_map"].get(str(node_id), [])


def _node_name(it):
    en = (it.get("label") or "").split(":")[-1].strip()
    zh = (it.get("nodeLabelLocale") or "").strip()
    if zh and zh != en:
        return f"{en}（{zh}）"
    return en or zh or str(it.get("id"))


def _node_result(it):
    return {
        "name": _node_name(it),
        "node_path": str(it.get("id")),
        "product_count": it.get("products", 0) or 0,
        "locale_path": it.get("nodeLabelPathLocale") or it.get("nodeLabelLocale") or "",
    }


def _ancestors(iid):
    """id 路径的所有前缀（从根到自身），用于重建路径栈。"""
    parts = str(iid).split(":")
    return [":".join(parts[:k]) for k in range(1, len(parts) + 1)]


def browse(cookie_file=None, max_show=30, _in=None, tree=None):
    """交互式逐级下钻品类树，返回 (name, node_path) 或 None（取消）。

    导航：数字=进入子类 / b=返回上级 / c=选定当前类 / s=关键词搜跳转 / m=手动填 / q=取消。
    任意层级都能选定（非叶子类目也可抓，范围更大）。

    _in: 注入 input 函数（测试用），默认内置 input。
    tree: 注入树（测试用），默认从缓存读。
    """
    _in = _in or input
    idx = build_index(tree=tree, cookie_file=cookie_file)
    if not idx["roots"]:
        print("[browse] 类目树为空（先跑 fetch_tree 刷新缓存），回退手动填。")
        return None

    current = None   # 当前节点 id；None = 顶层
    stack = []       # 路径栈（根→current），始终 == _ancestors(current)

    while True:
        if current is None:
            print(f"\n=== 顶层类目（{len(idx['roots'])} 个根）===")
            kids = idx["roots"]
        else:
            node = idx["by_id"][current]
            crumb = " > ".join(_node_name(idx["by_id"].get(p, {})) for p in stack)
            has_child = bool(idx["children_map"].get(current))
            print(f"\n=== {crumb}  （约{node.get('products', 0):,}商品 · "
                  f"{'有子类' if has_child else '叶子类目'} · node={current}）")
            kids = idx["children_map"].get(current, [])

        shown = kids[:max_show]
        for i, it in enumerate(shown, 1):
            nc = len(idx["children_map"].get(str(it.get("id")), []))
            tag = f"[{nc}子类]" if nc else "[叶子]"
            print(f"  {i:>2}) {tag} {_node_name(it):<36} 约{(it.get('products') or 0):,}商品")
        if len(kids) > max_show:
            print(f"  …共 {len(kids)} 个，仅显示前 {max_show}（用 s 关键词搜可精确跳转）")
        if not kids:
            print("  （无子类：c 选定此类，或 b 返回）")

        hint = "选(数字进入" + (", b 返回" if stack else "") + ", c 选定当前, s 搜, m 手动, q 取消): "
        s = _in(hint).strip().lower()

        if s == "q":
            return None
        elif s == "b" and stack:
            stack.pop()
            current = stack[-1] if stack else None
        elif s == "c":
            if current is None:
                print("  先进入一个类目再选定。")
                continue
            res = _node_result(idx["by_id"][current])
            print(f"  ✓ 选定: {res['name']}  ({res['locale_path']})  "
                  f"node={res['node_path']}  约{res['product_count']:,}商品")
            return res["name"], res["node_path"]
        elif s == "s":
            kw = _in("  关键词(中/英): ").strip()
            hits = search(kw)
            if not hits:
                print("  未命中，继续浏览。")
                continue
            top = hits[:max_show]
            for i, h in enumerate(top, 1):
                print(f"    {i}) {h['name']:<30} {h['locale_path'][:34]:<34} 约{h['product_count']:,}商品")
            pick = _in(f"  选(1-{len(top)} 跳转进入, 0 取消): ").strip()
            if pick.isdigit() and 1 <= int(pick) <= len(top):
                nid = top[int(pick) - 1]["node_path"]
                stack = _ancestors(nid)
                current = nid
        elif s == "m":
            node = _in("  输入 node 路径(如 2619525011:3741271:3741281): ").strip()
            if node:
                label = _in("  类目名(可选, 回车用 node): ").strip() or node
                return label, node
        elif s.isdigit() and shown and 1 <= int(s) <= len(shown):
            nid = str(shown[int(s) - 1]["id"])
            stack.append(nid)
            current = nid
        else:
            print("  无效输入。")
