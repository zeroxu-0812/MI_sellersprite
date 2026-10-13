import sys
import json
from pathlib import Path
import pandas as pd
import pytest

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
from run_all import to_mi_long_table, run_mi, recommend_bands


@pytest.fixture(scope="module")
def input_xlsx(tmp_path_factory, raw_json_path):
    data = json.load(open(raw_json_path, encoding="utf-8"))
    df = to_mi_long_table(data)
    out = tmp_path_factory.mktemp("run") / "input.xlsx"
    df.to_excel(out, index=False)
    return out


def test_run_mi_produces_report_or_keeps_partial(input_xlsx, tmp_path):
    out_dir = tmp_path / "mi_out"
    bands = recommend_bands(str(input_xlsx))
    report = run_mi(str(input_xlsx), currency="$", purpose="整体市场调研",
                    bands=bands, fmt="html", out_dir=str(out_dir))
    # module5 崩溃时 run.py 中断 → report 可能为 None；但 cleaned/ 产物应已生成
    cleaned = out_dir / "cleaned"
    assert cleaned.exists(), "MI 清洗产物未生成"
    if report is not None:
        assert Path(report).exists()
        assert Path(report).stat().st_size > 100_000   # HTML > 100KB


def test_cli_offline_input_bypass(raw_json_path, tmp_path):
    """--input 传 raw.json → 转换 + MI 报告，不触发抓取。"""
    import subprocess
    out_dir = tmp_path / "cli_out"
    cmd = [
        str(PROJECT / "MI_auto" / ".venv" / "bin" / "python"),
        str(PROJECT / "run_all.py"),
        "--market", "US",
        "--input", str(raw_json_path),
        "--format", "html",
        "--output", str(out_dir),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, f"CLI 失败:\n{r.stderr[-2000:]}"
    runs = list(out_dir.glob("*"))
    assert runs, "无运行目录产出"
    run_dir = runs[0]
    assert (run_dir / "input.xlsx").exists()
    assert (run_dir / "cleaned").exists()


def test_cli_empty_data_returns_5(tmp_path):
    """转换后 0 行（raw.json 为空数组）→ 退出码 5，不进入 MI。"""
    import subprocess
    empty_raw = tmp_path / "empty_raw.json"
    empty_raw.write_text(json.dumps([]), encoding="utf-8")
    out_dir = tmp_path / "empty_out"
    cmd = [
        str(PROJECT / "MI_auto" / ".venv" / "bin" / "python"),
        str(PROJECT / "run_all.py"),
        "--market", "US",
        "--input", str(empty_raw),
        "--output", str(out_dir),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    assert r.returncode == 5, (
        f"期望退出码 5，实际 {r.returncode}\nstdout:\n{r.stdout[-1000:]}\n"
        f"stderr:\n{r.stderr[-1000:]}")
