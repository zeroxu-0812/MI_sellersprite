import json
from unittest.mock import patch
from stages import crawl


def test_markets_has_10_including_in_mx():
    assert "IN" in crawl.MARKETS and "MX" in crawl.MARKETS
    assert crawl.MARKETS["IN"] == "₹"
    assert crawl.MARKETS["MX"] == "Mex$"
    assert len(crawl.MARKETS) == 10


def test_ensure_cookie_fresh_refreshes_when_exp_past(tmp_path, monkeypatch):
    cookie = tmp_path / "c.txt"
    cookie.write_text("Sprite-X-Token=eyJhbGciOiJIUzI1NiJ9."
                      # payload {"exp":1} base64url（早已过期）
                      "eyJleHAiOjF9.sig")
    called = {"n": 0}

    def fake_refresh(cookie_file=None, browser="chrome"):
        called["n"] += 1

    monkeypatch.setattr(crawl, "refresh", fake_refresh)
    crawl.ensure_cookie_fresh(cookie_file=str(cookie))
    assert called["n"] == 1


def test_ensure_cookie_fresh_skips_when_valid(tmp_path, monkeypatch):
    import time
    cookie = tmp_path / "c.txt"
    # payload {"exp": <now+3600>} → 仍有效
    import base64
    payload = base64.urlsafe_b64encode(json.dumps({"exp": int(time.time()) + 3600}).encode()).rstrip(b"=").decode()
    cookie.write_text(f"Sprite-X-Token=H.{payload}.sig")
    monkeypatch.setattr(crawl, "refresh", lambda **k: (_ for _ in ()).throw(AssertionError("不该刷新")))
    crawl.ensure_cookie_fresh(cookie_file=str(cookie))  # 不抛即通过


def test_run_writes_raw_and_meta(tmp_path):
    fake_data = [{"asin": "B1", "brand": "X", "price": 10, "rating": 4,
                  "reviews": 1, "available_days": 5, "amz_unit_trends": [{"dk": "202605", "sales": 7}]}]
    from run_dir import new_run_dir
    p = new_run_dir("US", "X", base=tmp_path)
    with patch("stages.crawl.ensure_cookie_fresh"), \
         patch("stages.crawl.fetch_category", return_value=fake_data) as fc, \
         patch("stages.crawl.probe_total", return_value=1), \
         patch("stages.crawl.raw_to_xlsx", return_value=(1, 1)):
        out = crawl.run("US", "X", "2619525011:3741271:3741281", run_dir=p, interactive=False)
    fc.assert_called_once()
    assert out.raw_json.exists()
    assert out.crawl_meta.exists()
    meta = json.loads(out.crawl_meta.read_text(encoding="utf-8"))
    assert meta["market"] == "US"
    assert meta["node_path"] == "2619525011:3741271:3741281"
