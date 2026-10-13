"""阶段 ③ 报告：input.xlsx → MI report.html（子进程调 MI/run.py，不改 MI）。"""
from run_all import recommend_bands, currency_for, run_mi


def _load_crawl_market(run_dir):
    if run_dir.crawl_meta.exists():
        import json
        return json.loads(run_dir.crawl_meta.read_text(encoding="utf-8")).get("market", "US")
    return "US"


def default_params(run_dir):
    market = _load_crawl_market(run_dir)
    return {
        "currency": currency_for(market),
        "purpose": "整体市场调研",
        "fmt": "html",
        "bands": recommend_bands(str(run_dir.input_xlsx)) if run_dir.input_xlsx.exists() else [10, 20, 30],
    }


def run(run_dir, purpose="整体市场调研", fmt="html", currency=None, bands=None):
    """调 MI/run.py 生成报告到 run_dir/mi_out/，返回报告路径或 None。"""
    market = _load_crawl_market(run_dir)
    currency = currency or currency_for(market)
    if bands is None:
        bands = recommend_bands(str(run_dir.input_xlsx))
    print(f"[report] bands={bands} currency={currency} format={fmt}")
    run_dir.mi_out.mkdir(parents=True, exist_ok=True)
    report_path = run_mi(str(run_dir.input_xlsx), currency, purpose, bands, fmt, str(run_dir.mi_out))
    if report_path is None:
        print(f"[report] ⚠️ MI 非零退出（常因 module5 新品饼图为空），部分产物见 {run_dir.mi_out}")
    else:
        print(f"[report] ✅ {report_path}")
    return report_path
