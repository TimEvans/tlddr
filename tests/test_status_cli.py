import json
from pathlib import Path
from tlddr.cli import main
from tlddr.runstate import init_state


def test_status_cli_reports_no_run(tmp_path, capsys):
    assert main(["status", "--output", str(tmp_path)]) == 0
    assert "no run" in capsys.readouterr().out.lower()


def test_mark_stage_then_status(tmp_path, capsys):
    assert main(["mark-stage", "extract", "--output", str(tmp_path)]) == 0
    assert main(["status", "--output", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "extract" in out and "done" in out
    # state_lock landed in the hidden bin
    assert (tmp_path / ".tlddr" / "state_lock.json").exists()
