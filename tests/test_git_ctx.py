"""Tests for GitContext."""
import subprocess
from pathlib import Path

import pytest

from haac.git_ctx import GitContext


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    return tmp_path


def _commit(repo: Path, path: str, content: str, msg: str = "x") -> None:
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text(content)
    subprocess.run(["git", "add", path], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=repo, check=True)


def test_is_repo_true(git_repo):
    assert GitContext(git_repo).is_repo() is True


def test_is_repo_false(tmp_path):
    assert GitContext(tmp_path).is_repo() is False


def test_head_blob_returns_content(git_repo):
    _commit(git_repo, "state/x.yaml", "hello\n")
    assert GitContext(git_repo).head_blob(Path("state/x.yaml")) == "hello\n"


def test_head_blob_returns_none_for_untracked(git_repo):
    _commit(git_repo, "seed.txt", "x")
    assert GitContext(git_repo).head_blob(Path("state/missing.yaml")) is None


def test_head_blob_returns_none_when_no_head(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    assert GitContext(tmp_path).head_blob(Path("anything.yaml")) is None


def test_ls_files_respects_gitignore(git_repo):
    _commit(git_repo, ".gitignore", "ignored.yaml\n")
    _commit(git_repo, "tracked.yaml", "x")
    (git_repo / "ignored.yaml").write_text("y")
    (git_repo / "untracked.yaml").write_text("z")
    files = {p.as_posix() for p in GitContext(git_repo).ls_files()}
    assert "tracked.yaml" in files
    assert "ignored.yaml" not in files
    # untracked-but-not-ignored files DO appear in ls_files with --others
    assert "untracked.yaml" in files


def test_add_and_commit(git_repo):
    _commit(git_repo, "seed.txt", "x")
    new_file = git_repo / "new.yaml"
    new_file.write_text("content")
    ctx = GitContext(git_repo)
    ctx.add([Path("new.yaml")])
    ctx.commit("test: add new.yaml")
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=git_repo, capture_output=True, text=True, check=True
    ).stdout
    assert "test: add new.yaml" in log


def test_changed_vs_head(git_repo):
    _commit(git_repo, "a.yaml", "orig\n")
    (git_repo / "a.yaml").write_text("modified\n")
    ctx = GitContext(git_repo)
    assert ctx.differs_from_head(Path("a.yaml")) is True
    assert ctx.differs_from_head(Path("nonexistent.yaml")) is False
