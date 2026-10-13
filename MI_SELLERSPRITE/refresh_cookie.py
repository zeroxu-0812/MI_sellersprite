#!/usr/bin/env python3
"""从浏览器读取 sellersprite.com cookie，自动刷新 .superpowers/sdd/v3_cookie.txt。

前提：你在 Chrome（或 Firefox）里登录着 sellersprite.com——浏览器会自动维持会话，
脚本只读浏览器已有的 cookie，不模拟登录，零封号风险。把原来"手动抓 curl 粘文件"
这步自动化。

macOS 首次运行可能弹"xxx 想使用 Chrome Safe Storage 钥匙串"——点"始终允许"。

用法：
  python refresh_cookie.py                 # 默认从 Chrome 读
  python refresh_cookie.py --browser firefox
"""
import argparse
import base64
import json
import time
from pathlib import Path

import browser_cookie3

DEFAULT_COOKIE_FILE = (
    Path(__file__).resolve().parents[1] / ".superpowers" / "sdd" / "v3_cookie.txt"
)


def _jwt_exp(token):
    """解 JWT payload 取 exp（不过校验签名，只看时效）。"""
    try:
        payload = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "==")).get("exp")
    except Exception:
        return None


def _probe_ok(cookie_str, attempts=3):
    """刷新后探测 competing-lookup，验证 cookie 真能取数。

    browser_cookie3 在某些 Chrome 版本会损坏 cookie 值（实测把 JWT 里一个字节
    翻转，ph↔pi），导致服务端签名校验失败、静默回 code:OK data:null。损坏是
    确定性的，限流是瞬时的，故多次探测：有任一次拿到 dict data 即视为有效。

    返回 True=有效 / False=损坏或持续空 / None=无法验证（standalone 缺 website_scraper）。
    """
    try:
        import website_scraper as ws
    except Exception:
        return None
    body = {"market": "US", "monthName": "bsr_sales", "asins": [], "page": 1,
            "nodeIdPaths": ["2619525011:3741271:3741281"], "symbolFlag": False, "size": 1,
            "order": {"field": "total_units", "desc": True}, "lowPrice": "N", "salesGrowthType": "30d"}
    try:
        headers = ws._headers(cookie_str, body)
    except Exception:
        return False
    for _ in range(attempts):
        try:
            d = ws._post_page(headers, body, throttle_retries=0)
            if isinstance(d.get("data"), dict):
                return True
        except ws.SessionExpired:
            return False
        except Exception:
            pass
        time.sleep(2)
    return False


def refresh(cookie_file=None, browser="chrome"):
    cookie_file = Path(cookie_file or DEFAULT_COOKIE_FILE)

    loader = {"chrome": browser_cookie3.chrome,
              "firefox": browser_cookie3.firefox}.get(browser)
    if loader is None:
        raise SystemExit(f"不支持 browser={browser}")

    jar = loader(domain_name="sellersprite.com")

    # 拼 name=value; ...，覆盖 .sellersprite.com 与 www.sellersprite.com 两个 host
    pairs, seen, token = [], set(), None
    for c in jar:
        key = (c.domain, c.name)
        if key in seen or c.value is None:
            continue
        seen.add(key)
        pairs.append(f"{c.name}={c.value}")
        if c.name == "Sprite-X-Token":
            token = c.value

    if not token:
        raise SystemExit(
            "❌ 没读到 Sprite-X-Token——先在浏览器登录 sellersprite.com、"
            "访问一下 competing-lookup 页面触发会话，再跑本脚本")

    exp = _jwt_exp(token)
    if exp:
        left = exp - int(time.time())
        flag = (f"剩 {left // 3600}h" if left > 0
                else f"已过期 {(-left) // 3600}h（Chrome 里访问 sellersprite 触发续期后再跑）")
        print(f"Sprite-X-Token exp: {time.strftime('%Y-%m-%d %H:%M', time.localtime(exp))} → {flag}")

    cookie_str = "; ".join(pairs)

    if cookie_file.exists():  # 备份旧 cookie
        bak = cookie_file.with_suffix(".txt.bak")
        bak.write_text(cookie_file.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"旧 cookie 备份 → {bak}")

    cookie_file.parent.mkdir(parents=True, exist_ok=True)
    cookie_file.write_text(cookie_str, encoding="utf-8")
    print(f"✓ 已刷新 {cookie_file}（{len(pairs)} 个 cookie）")

    ok = _probe_ok(cookie_str)
    if ok is True:
        print("✓ cookie 探测通过（competing-lookup 可正常取数）")
    elif ok is False:
        print("⚠️ 刷新后的 cookie 探测仍返回空数据——browser_cookie3 可能损坏了 JWT（已知 bug）。")
        print("   请在 Chrome competing-lookup 页 F12 → Network → 右键 competing-lookup 请求")
        print("   → Copy as cURL，把 -b '...' 里整段 cookie 粘到该文件后重跑：")
        print(f"     {cookie_file}")
    return cookie_str


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="从浏览器刷新 sellersprite cookie")
    ap.add_argument("--cookie", default=str(DEFAULT_COOKIE_FILE))
    ap.add_argument("--browser", default="chrome", choices=["chrome", "firefox"])
    a = ap.parse_args()
    refresh(a.cookie, a.browser)
