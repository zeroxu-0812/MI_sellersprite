"""run 目录与产物路径的统一管理（三段式管线可分可合的状态单元）。"""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DEFAULT_BASE = Path(__file__).resolve().parent / "output"


@dataclass
class RunPaths:
    root: Path

    @property
    def raw_json(self):
        return self.root / "raw.json"

    @property
    def raw_xlsx(self):
        return self.root / "raw.xlsx"

    @property
    def crawl_meta(self):
        return self.root / "crawl_meta.json"

    @property
    def input_xlsx(self):
        return self.root / "input.xlsx"

    @property
    def clean_meta(self):
        return self.root / "clean_meta.json"

    @property
    def mi_out(self):
        return self.root / "mi_out"

    @property
    def report_html(self):
        if not self.mi_out.exists():
            return None
        reports = sorted(self.mi_out.glob("report_*.html"))
        return reports[-1] if reports else None


def _safe_label(label: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in label)[:40]


def new_run_dir(market: str, cat_label: str, base=DEFAULT_BASE) -> RunPaths:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    root = Path(base) / f"{market}_{_safe_label(cat_label)}_{ts}"
    root.mkdir(parents=True, exist_ok=True)
    return RunPaths(root)


def list_run_dirs(base=DEFAULT_BASE):
    base = Path(base)
    if not base.exists():
        return []
    out = []
    for d in base.iterdir():
        if d.is_dir():
            p = RunPaths(d)
            if p.raw_json.exists() or p.input_xlsx.exists():
                out.append(p)
    out.sort(key=lambda p: p.root.name, reverse=True)  # 时间戳降序
    return out


def stage_done(paths: RunPaths, stage: str) -> bool:
    if stage == "crawl":
        return paths.raw_json.exists()
    if stage == "clean":
        return paths.input_xlsx.exists()
    if stage == "report":
        return paths.report_html is not None
    return False
