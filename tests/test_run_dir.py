from pathlib import Path
from run_dir import RunPaths, new_run_dir, list_run_dirs, stage_done


def test_new_run_dir_creates_dir(tmp_path):
    p = new_run_dir("US", "Dishwashers", base=tmp_path)
    assert p.root.exists() and p.root.is_dir()
    assert p.raw_json == p.root / "raw.json"
    assert p.mi_out == p.root / "mi_out"
    assert "US" in p.root.name and "Dishwashers" in p.root.name


def test_safe_label_replaces_unsafe(tmp_path):
    p = new_run_dir("US", "运动水杯/水瓶?", base=tmp_path)
    assert "/" not in p.root.name and "?" not in p.root.name


def test_list_run_dirs_finds_only_data_dirs(tmp_path):
    # 有 raw.json 的算，空目录不算
    a = new_run_dir("US", "A", base=tmp_path)
    a.raw_json.write_text("[]")
    new_run_dir("US", "B", base=tmp_path)  # 空目录，不应被列出
    found = list_run_dirs(base=tmp_path)
    assert len(found) == 1
    assert found[0].raw_json.exists()


def test_stage_done_detection(tmp_path):
    p = new_run_dir("US", "X", base=tmp_path)
    assert stage_done(p, "crawl") is False
    p.raw_json.write_text("[]")
    assert stage_done(p, "crawl") is True
    assert stage_done(p, "clean") is False
    p.input_xlsx.write_text("x")
    assert stage_done(p, "clean") is True
