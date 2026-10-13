import json
from unittest.mock import patch
from stages import report


def test_default_params_reads_crawl_meta(tmp_path):
    from run_dir import new_run_dir
    p = new_run_dir("JP", "X", base=tmp_path)
    p.crawl_meta.write_text(json.dumps({"market": "JP", "category": "X"}), encoding="utf-8")
    p.input_xlsx.write_text("dummy")  # recommend_bands 会读，下面 mock 掉
    with patch("stages.report.recommend_bands", return_value=[10, 20, 30]):
        params = report.default_params(p)
    assert params["currency"] == "¥"  # currency_for("JP")
    assert params["bands"] == [10, 20, 30]
    assert params["purpose"] == "整体市场调研"
    assert params["fmt"] == "html"


def test_run_invokes_run_mi_and_returns_report(tmp_path):
    from run_dir import new_run_dir
    p = new_run_dir("US", "X", base=tmp_path)
    p.crawl_meta.write_text(json.dumps({"market": "US"}), encoding="utf-8")
    p.input_xlsx.write_text("dummy")
    p.mi_out.mkdir()
    fake_report = p.mi_out / "report_20260720.html"
    with patch("stages.report.recommend_bands", return_value=[15, 25, 35]), \
         patch("stages.report.run_mi", return_value=fake_report) as mock_mi:
        out = report.run(p)
    assert out == fake_report
    mock_mi.assert_called_once()
    args = mock_mi.call_args.args
    assert args[0] == str(p.input_xlsx)
    assert args[1] == "$"  # US currency
