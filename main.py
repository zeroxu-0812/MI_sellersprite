#!/usr/bin/env python3
"""卖家精灵市场洞察 · 三段式交互管线主菜单。"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "MI_auto"))
sys.path.insert(0, str(PROJECT_ROOT / "MI_SELLERSPRITE"))

from stages import crawl, clean, report          # noqa: E402
from run_dir import list_run_dirs, RunPaths      # noqa: E402
from refresh_cookie import refresh               # noqa: E402

MENU = """
====== 卖家精灵市场洞察 ======
  1) 全流程（采集 → 清洗 → 报告）
  2) 仅采集
  3) 从已有数据继续（清洗 + 报告）
  4) 仅清洗（选已有 run 目录）
  5) 仅报告（选已有 run 目录）
  6) 刷新 cookie（从 Chrome 读）
  0) 退出
选: """


def _pick_run(prompt="选 run 目录: ") -> RunPaths:
    runs = list_run_dirs()
    if not runs:
        print("没有历史 run 目录（先采集一次）。")
        return None
    for i, p in enumerate(runs, 1):
        print(f"  {i}) {p.root.name}")
    s = input(prompt).strip()
    if s.isdigit() and 1 <= int(s) <= len(runs):
        return runs[int(s) - 1]
    return None


def _do_crawl() -> RunPaths:
    return crawl.run()


def _do_clean(paths: RunPaths) -> RunPaths:
    if paths is None:
        paths = _pick_run()
    if paths is None:
        return None
    clean.run(paths)
    return paths


def _do_report(paths: RunPaths):
    if paths is None:
        paths = _pick_run()
    if paths is None:
        return
    report.run(paths)


def main():
    while True:
        try:
            choice = input(MENU).strip()
        except EOFError:
            print("\n再见。")
            return
        try:
            if choice == "0":
                print("再见。")
                return
            elif choice == "1":
                p = _do_crawl()
                _do_clean(p)
                _do_report(p)
            elif choice == "2":
                _do_crawl()
            elif choice == "3":
                p = _pick_run()
                if p:
                    _do_clean(p)
                    _do_report(p)
            elif choice == "4":
                _do_clean(None)
            elif choice == "5":
                _do_report(None)
            elif choice == "6":
                refresh()
            else:
                print("无效选项。")
        except Exception as e:
            print(f"[ERROR] {e}")


if __name__ == "__main__":
    main()
