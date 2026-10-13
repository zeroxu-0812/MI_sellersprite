import io

import main


def test_main_eof_exits_cleanly(monkeypatch, capsys):
    """stdin 立即 EOF（管道耗尽 / Ctrl+D）→ main() 干净返回，不抛 EOFError。"""
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert main.main() is None
    assert "再见" in capsys.readouterr().out
