import json
import sys

import pytest

from alpha_lab.cli import main


def test_health_cli_fails_nonzero_but_saves_diagnostic_report(tmp_path, monkeypatch, capsys):
    output=tmp_path/"health.json"
    monkeypatch.setattr(sys, "argv", [
        "alpha-lab", "health", "--input-dir", str(tmp_path/"empty"),
        "--asof", "2026-10-28", "--out", str(output), "--fail-on-blocked"
    ])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code==2
    assert output.is_file()
    report=json.loads(output.read_text(encoding="utf-8"))
    assert report["status"]=="BLOCKED_DATA_HEALTH"
    assert "BLOCKED_DATA_HEALTH" in capsys.readouterr().out
