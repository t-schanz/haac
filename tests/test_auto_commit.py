"""Tests for scoped auto-commit after apply."""
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "seed.txt").write_text("")
    subprocess.run(["git", "-C", str(tmp_path), "add", "seed.txt"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-q", "-m", "init"], check=True)
    return tmp_path


def test_auto_commit_adds_only_touched_paths(repo):
    from haac.cli import _do_auto_commit
    from haac.config import Config

    # haac touched this one
    (repo / "state").mkdir()
    (repo / "state" / "entities.yaml").write_text("haac_id: x\n")

    # unrelated modification — must NOT be committed
    (repo / "unrelated.txt").write_text("user work")
    subprocess.run(["git", "-C", str(repo), "add", "unrelated.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "user"], check=True)
    (repo / "unrelated.txt").write_text("user work in progress")

    config = Config(ha_url="x", ha_token="t", state_dir=repo / "state", project_dir=repo)
    touched = {Path("state/entities.yaml")}

    _do_auto_commit(config, touched, "haac: apply — test", mode="yes")

    log = subprocess.run(
        ["git", "-C", str(repo), "log", "--format=%s"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "haac: apply — test" in log

    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "unrelated.txt" in status


def test_auto_commit_skipped_when_no_touched_paths(repo):
    from haac.cli import _do_auto_commit
    from haac.config import Config

    config = Config(ha_url="x", ha_token="t", state_dir=repo / "state", project_dir=repo)
    _do_auto_commit(config, set(), "msg", mode="yes")
    log = subprocess.run(
        ["git", "-C", str(repo), "log", "--format=%s"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "msg" not in log


def test_auto_commit_no_mode_skips(repo):
    from haac.cli import _do_auto_commit
    from haac.config import Config

    (repo / "a.yaml").write_text("x")
    config = Config(ha_url="x", ha_token="t", state_dir=repo, project_dir=repo)
    _do_auto_commit(config, {Path("a.yaml")}, "msg", mode="no")
    log = subprocess.run(
        ["git", "-C", str(repo), "log", "--format=%s"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "msg" not in log
