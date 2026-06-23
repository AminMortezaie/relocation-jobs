"""reset_password CLI main() with patched argv."""

from __future__ import annotations

import pytest
from werkzeug.security import check_password_hash
from tests.helpers.passwords import hash_test_password

from relocation_jobs.db import create_user, get_user_by_username
from relocation_jobs.reset_password import main


@pytest.mark.integration
def test_main_updates_password(db, monkeypatch):
    create_user("cliuser", hash_test_password("oldpass123"))
    monkeypatch.setattr(
        "sys.argv",
        ["reset_password.py", "cliuser", "newpass12345"],
    )
    assert main() == 0
    row = get_user_by_username("cliuser")
    assert check_password_hash(row["password_hash"], "newpass12345")


@pytest.mark.integration
def test_main_missing_password(db, monkeypatch, capsys):
    monkeypatch.setattr("relocation_jobs.reset_password._load_env", lambda: None)
    monkeypatch.delenv("PANEL_ADMIN_PASSWORD", raising=False)
    monkeypatch.setattr("sys.argv", ["reset_password.py", "admin"])
    assert main() == 1
    assert "Password required" in capsys.readouterr().err


@pytest.mark.integration
def test_main_user_not_found(db, monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        ["reset_password.py", "ghost", "newpass12345"],
    )
    assert main() == 1
    assert "User not found" in capsys.readouterr().err


@pytest.mark.integration
def test_main_rename_from(db, monkeypatch, capsys):
    create_user("oldname", hash_test_password("oldpass123"))
    monkeypatch.setattr(
        "sys.argv",
        [
            "reset_password.py",
            "newname",
            "newpass12345",
            "--rename-from",
            "oldname",
        ],
    )
    assert main() == 0
    out = capsys.readouterr().out
    assert "Renamed oldname" in out
    assert get_user_by_username("newname") is not None
    assert get_user_by_username("oldname") is None


@pytest.mark.integration
def test_main_rename_from_missing_user(db, monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        [
            "reset_password.py",
            "target",
            "newpass12345",
            "--rename-from",
            "missing",
        ],
    )
    assert main() == 1
    assert "User not found: missing" in capsys.readouterr().err


@pytest.mark.integration
def test_main_rename_username_taken(db, monkeypatch, capsys):
    create_user("holder", hash_test_password("pass123456"))
    create_user("oldname", hash_test_password("pass123456"))
    monkeypatch.setattr(
        "sys.argv",
        [
            "reset_password.py",
            "holder",
            "newpass12345",
            "--rename-from",
            "oldname",
        ],
    )
    assert main() == 1
    assert "Username already taken" in capsys.readouterr().err


@pytest.mark.integration
def test_main_module_entry(db, monkeypatch):
    create_user("admin", hash_test_password("pass123456"))
    monkeypatch.setattr(
        "sys.argv",
        ["reset_password.py", "admin", "newpass12345"],
    )
    with pytest.raises(SystemExit) as exc:
        import runpy
        runpy.run_module("relocation_jobs.reset_password", run_name="__main__")
    assert exc.value.code == 0


@pytest.mark.integration
def test_load_env_with_dotenv(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("PANEL_ADMIN_PASSWORD=fromdotenv\n", encoding="utf-8")
    monkeypatch.setattr("relocation_jobs.reset_password.PROJECT_ROOT", tmp_path)
    try:
        import dotenv  # noqa: F401
    except ImportError:
        pytest.skip("python-dotenv not installed")
    from relocation_jobs.reset_password import _load_env

    monkeypatch.delenv("PANEL_ADMIN_PASSWORD", raising=False)
    _load_env()
    import os
    assert os.environ.get("PANEL_ADMIN_PASSWORD") == "fromdotenv"


@pytest.mark.integration
@pytest.mark.fresh_db
def test_main_uses_env_defaults(db, monkeypatch):
    create_user("admin", hash_test_password("old"))
    monkeypatch.setenv("PANEL_ADMIN_USER", "admin")
    monkeypatch.setenv("PANEL_ADMIN_PASSWORD", "fromenv123")
    monkeypatch.setattr("sys.argv", ["reset_password.py"])
    assert main() == 0
    row = get_user_by_username("admin")
    assert check_password_hash(row["password_hash"], "fromenv123")
