"""阶段 ② 清洗：raw.json → MI 长表 input.xlsx（保留 9 字段 + 最近 24 个月窗口）。"""
import json
from pathlib import Path

import pandas as pd

from run_all import infer_crawl_date
from sellersprite_to_mi import convert_data


def shift_month(ym: str, delta: int) -> str:
    """ym='YYYYMM'，加减 delta 月，返回 'YYYYMM'。delta 负数=更早。"""
    y, m = int(ym[:4]), int(ym[4:])
    idx = y * 12 + (m - 1) + delta
    ny, nm = divmod(idx, 12)
    return f"{ny:04d}{nm + 1:02d}"


def _valid_dk(dk):
    return isinstance(dk, str) and len(dk) == 6 and dk.isdigit() and 1 <= int(dk[4:]) <= 12


def window_for(data):
    """取 data 所有 amz_unit_trends 的最大 dk，返回 (start_dk, end_dk) = (max-23月, max)。"""
    dks = [str(t.get("dk", "")) for e in data for t in (e.get("amz_unit_trends") or [])]
    dks = [d for d in dks if _valid_dk(d)]
    end = max(dks) if dks else None
    if end is None:
        return None, None
    return shift_month(end, -23), end


def run(run_dir) -> Path:
    """读 run_dir/raw.json → 写 input.xlsx + clean_meta.json，返回 input.xlsx 路径。"""
    data = json.loads(run_dir.raw_json.read_text(encoding="utf-8"))
    if not data:
        raise RuntimeError("raw.json 为空，无可清洗数据")

    crawl = infer_crawl_date(data)
    df = convert_data(data, crawl, include_no_trends=True)
    if df.empty:
        raise RuntimeError("转换后 0 行（无有效 amz_unit_trends），无法分析")

    # 24 个月窗口裁剪：时间列 'YYYY-MM' → 'YYYYMM' 字符串比较（零填充字典序=时序）
    start_dk, end_dk = window_for(data)
    if start_dk is None:
        raise RuntimeError("无有效 amz_unit_trends 数据，无法分析")
    ym_to_dk = df["时间"].str.replace("-", "")
    df = df[(ym_to_dk >= start_dk) & (ym_to_dk <= end_dk)].copy()

    df.to_excel(run_dir.input_xlsx, index=False, engine="openpyxl")

    n_parent = df["ASIN"].nunique()
    no_trends = sum(1 for e in data if not (e.get("amz_unit_trends") or []))
    meta = {
        "window_start": f"{start_dk[:4]}-{start_dk[4:]}" if start_dk else None,
        "window_end": f"{end_dk[:4]}-{end_dk[4:]}" if end_dk else None,
        "month_count": 24,
        "rows": int(len(df)),
        "parent_asins": int(n_parent),
        "no_trends_injected": int(no_trends),
        "fields": list(df.columns),
    }
    run_dir.clean_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[clean] {len(df)} 行 / {n_parent} 父ASIN / 窗口 {meta['window_start']}~{meta['window_end']} → {run_dir.input_xlsx}")
    return run_dir.input_xlsx
