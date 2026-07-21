"""Tests for Windows startup registration + tray listening cue."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from donna.tools import setup_startup


def test_write_start_bat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup_startup, "project_root", lambda: tmp_path)
    (tmp_path / "run.py").write_text("# stub entry\n", encoding="utf-8")
    venv_scripts = tmp_path / ".venv" / "Scripts"
    venv_scripts.mkdir(parents=True)
    (venv_scripts / "pythonw.exe").write_bytes(b"")

    bat = setup_startup.write_start_bat()
    assert bat == tmp_path / "start_donna.bat"
    text = bat.read_text(encoding="utf-8")
    assert "run.py" in text
    assert "core_agent.py" not in text
    assert "pythonw.exe" in text
    print(f"[PASS] start_donna.bat written: {bat}")


def test_install_uninstall_status_mocked() -> None:
    fake_bat = Path("C:/fake/start_donna.bat")
    with (
        patch.object(setup_startup, "write_start_bat", return_value=fake_bat),
        patch.object(setup_startup.winreg, "OpenKey") as open_key,
        patch.object(setup_startup.winreg, "SetValueEx") as set_value,
        patch.object(setup_startup.winreg, "DeleteValue") as del_value,
        patch.object(
            setup_startup.winreg,
            "QueryValueEx",
            return_value=(f'"{fake_bat}"', setup_startup.winreg.REG_SZ),
        ),
    ):
        ctx = MagicMock()
        open_key.return_value.__enter__.return_value = ctx

        assert setup_startup.install() == 0
        set_value.assert_called_once()
        args = set_value.call_args[0]
        assert args[1] == setup_startup.VALUE_NAME
        assert "start_donna.bat" in str(args[4])

        assert setup_startup.status() == 0
        assert setup_startup.uninstall() == 0
        del_value.assert_called_once()
    print("[PASS] install/status/uninstall (mocked winreg)")


def test_tray_icon_listening_vs_idle() -> None:
    from donna.core_agent import create_tray_image

    idle = create_tray_image("idle")
    listening = create_tray_image("listening")
    assert idle.size == listening.size == (64, 64)
    # Center-ish pixel should differ (blue idle vs green listening fill).
    assert idle.getpixel((32, 10)) != listening.getpixel((32, 10))
    print("[PASS] tray listening icon differs from idle")
