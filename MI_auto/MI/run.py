#!/usr/bin/env python3
"""
run.py — Market Insight 一键运行入口

用法：
    python run.py --data <数据文件路径> --price-bands "[50,100,200,400]" [选项]

示例：
    python run.py --data ./data/FR10153400031.xlsx --price-bands "[50,100,200,400]"
    python run.py --data ./data/FR10153400031.xlsx --price-bands "[50,100,200,400]" --currency "€" --format pdf
    python run.py --data ./data/FR10153400031.xlsx --price-bands "[50,100,200,400]" --format all --output ./my_output

⚠️  AI 助手注意：运行本脚本前，必须先向用户确认以下 4 个问题：
    1. 核心商业目的（新品切入 / 竞品防御 / 整体调研）→ --purpose
    2. 价位段分组节点（可选预设/AI推荐/自定义）→ --price-bands
    3. 货币单位（$ / € / £ / ¥ 等）→ --currency
    4. 输出格式（html / pdf / ppt / all）→ --format
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

# 将 scripts/ 目录加入 Python 路径
SCRIPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts")
sys.path.insert(0, SCRIPT_DIR)


def run_step(desc: str, cmd: list):
    """执行子命令，失败时打印错误并退出。"""
    print(f"\n{'─'*60}")
    print(f"  {desc}")
    print(f"{'─'*60}")
    result = subprocess.run(cmd, capture_output=False, text=True)
    if result.returncode != 0:
        print(f"\n[ERROR] 步骤失败，退出码 {result.returncode}")
        sys.exit(result.returncode)


def main():
    parser = argparse.ArgumentParser(
        description="Market Insight 跨境电商市场洞察报告一键生成工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--data", required=True,
        help="原始数据文件路径（支持 .xlsx / .csv）"
    )
    parser.add_argument(
        "--price-bands", required=True,
        help='价位段分组，JSON 数组格式，例如 "[50,100,200,400]"'
    )
    parser.add_argument(
        "--purpose", default="整体市场调研",
        help='核心商业目的，默认为"整体市场调研"'
    )
    parser.add_argument(
        "--currency", default="$",
        help='货币单位符号，默认为 "$"，可选 "€"、"£"、"¥" 等'
    )
    parser.add_argument(
        "--format", default="html",
        choices=["html", "pdf", "ppt", "all"],
        help='输出格式：html（默认）/ pdf / ppt / all（同时输出三种）'
    )
    parser.add_argument(
        "--output", default="./output",
        help="输出目录，默认为 ./output"
    )
    args = parser.parse_args()

    # ── 路径解析 ──────────────────────────────────────────────────────────────
    data_path   = os.path.abspath(args.data)
    output_dir  = os.path.abspath(args.output)
    cleaned_dir = os.path.join(output_dir, "cleaned")
    charts_dir  = os.path.join(output_dir, "charts")
    charts_excl = os.path.join(output_dir, "charts_excl")
    price_bands = args.price_bands
    currency    = args.currency
    fmt         = args.format

    os.makedirs(cleaned_dir, exist_ok=True)
    os.makedirs(charts_dir,  exist_ok=True)

    python = sys.executable
    clean_script   = os.path.join(SCRIPT_DIR, "clean_data.py")
    charts_script  = os.path.join(SCRIPT_DIR, "generate_charts.py")
    ai_script      = os.path.join(SCRIPT_DIR, "ai_analysis.py")
    report_script  = os.path.join(SCRIPT_DIR, "generate_report.py")
    export_script  = os.path.join(SCRIPT_DIR, "export.py")

    print("\n" + "═"*60)
    print("  Market Insight — 跨境电商市场洞察报告生成器")
    print("═"*60)
    print(f"  数据文件  : {data_path}")
    print(f"  价位段    : {price_bands}")
    print(f"  货币单位  : {currency}")
    print(f"  商业目的  : {args.purpose}")
    print(f"  输出格式  : {fmt}")
    print(f"  输出目录  : {output_dir}")

    # ── 阶段一：数据清洗 ───────────────────────────────────────────────────────
    run_step(
        "阶段一：数据清洗与特征提取",
        [python, clean_script, data_path, price_bands, cleaned_dir,
         "--currency", currency],
    )

    # 读取 meta.json，判断是否存在头部品牌
    meta_path = os.path.join(cleaned_dir, "meta.json")
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    has_dominant = meta.get("has_dominant_brand", False)
    dominant     = meta.get("dominant_brand", "")
    dominant_pct = meta.get("dominant_brand_share_pct", 0)

    if has_dominant:
        print(f"\n  ⚠  检测到头部品牌：{dominant}（份额 {dominant_pct:.1f}%）")
        print(f"     将额外生成去除 {dominant} 版报告。")

    # 验证 module6 非空
    m6_path = os.path.join(cleaned_dir, "module6_asin_efficiency.json")
    with open(m6_path, "r", encoding="utf-8") as f:
        m6 = json.load(f)
    top10_count = len(m6.get("top10_efficiency", []))
    if top10_count == 0:
        print("\n  [WARNING] module6 top10_efficiency 为空！")
        print("  请检查原始数据中是否存在 Review Count / review count 列。")
    else:
        print(f"\n  ✓ module6 验证通过：top10_efficiency 共 {top10_count} 行")

    # ── 阶段二：可视化图表 ─────────────────────────────────────────────────────
    run_step(
        "阶段二：生成完整版可视化图表",
        [python, charts_script, cleaned_dir, charts_dir,
         "--currency", currency],
    )
    if has_dominant:
        os.makedirs(charts_excl, exist_ok=True)
        run_step(
            f"阶段二（去除 {dominant} 版）：生成去除头部品牌可视化图表",
            [python, charts_script, cleaned_dir, charts_excl,
             "--suffix", "_excl", "--currency", currency],
        )

    # ── 阶段三：AI 深度分析 ────────────────────────────────────────────────────
    run_step(
        "阶段三：AI 深度分析（完整版 + 去除头部品牌版）",
        [python, ai_script, cleaned_dir, output_dir, args.purpose,
         "--currency", currency],
    )
    # ai_analysis.py 内部会自动判断 has_dominant_brand 并生成 _excl 版

    # ── 阶段四：HTML 报告整合 ──────────────────────────────────────────────────
    analysis_json      = os.path.join(output_dir, "analysis.json")
    analysis_excl_json = os.path.join(output_dir, "analysis_excl.json")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_html        = os.path.join(output_dir, f"report_{timestamp}.html")
    report_excl_html   = os.path.join(output_dir, f"report_excl_{timestamp}.html")

    run_step(
        "阶段四：整合生成完整版 HTML 报告",
        [python, report_script, analysis_json, charts_dir, report_html, cleaned_dir,
         "--currency", currency],
    )
    if has_dominant and os.path.exists(analysis_excl_json):
        run_step(
            f"阶段四（去除 {dominant} 版）：整合生成去除头部品牌版 HTML 报告",
            [
                python, report_script,
                analysis_excl_json, charts_excl, report_excl_html, cleaned_dir,
                "--excl", "--currency", currency,
            ],
        )

    # ── 阶段五：导出 PDF / PPT（按需）────────────────────────────────────────
    export_fmt = None
    if fmt == "pdf":
        export_fmt = "pdf"
    elif fmt == "ppt":
        export_fmt = "ppt"
    elif fmt == "all":
        export_fmt = "all"

    if export_fmt:
        run_step(
            f"阶段五：导出 {export_fmt.upper()} 格式（完整版）",
            [python, export_script, report_html, "--format", export_fmt],
        )
        if has_dominant and os.path.exists(report_excl_html):
            run_step(
                f"阶段五（去除 {dominant} 版）：导出 {export_fmt.upper()} 格式",
                [python, export_script, report_excl_html, "--format", export_fmt],
            )

    # ── 完成 ──────────────────────────────────────────────────────────────────
    print("\n" + "═"*60)
    print("  ✅  全部完成！报告已生成：")
    print(f"     完整版 HTML       → {report_html}")
    if fmt in ("pdf", "all"):
        pdf_path = report_html.replace(".html", ".pdf")
        if os.path.exists(pdf_path):
            print(f"     完整版 PDF        → {pdf_path}")
    if fmt in ("ppt", "all"):
        ppt_path = report_html.replace(".html", ".pptx")
        if os.path.exists(ppt_path):
            print(f"     完整版 PPT        → {ppt_path}")
    if has_dominant and os.path.exists(report_excl_html):
        print(f"     去除头部品牌版 HTML → {report_excl_html}")
        if fmt in ("pdf", "all"):
            pdf_excl = report_excl_html.replace(".html", ".pdf")
            if os.path.exists(pdf_excl):
                print(f"     去除头部品牌版 PDF  → {pdf_excl}")
        if fmt in ("ppt", "all"):
            ppt_excl = report_excl_html.replace(".html", ".pptx")
            if os.path.exists(ppt_excl):
                print(f"     去除头部品牌版 PPT  → {ppt_excl}")
    print("═"*60 + "\n")


if __name__ == "__main__":
    main()
