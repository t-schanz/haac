"""Tests for repo-wide reference scanning and rewriting."""
import subprocess
from pathlib import Path

import pytest

from haac.git_ctx import GitContext
from haac.rename_refs import scan_references, rewrite_references


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text(".venv/\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", ".gitignore"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-q", "-m", "init"], check=True)
    return tmp_path


def _write(repo: Path, rel: str, content: str):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def test_scan_finds_token_matches(repo):
    _write(repo, "scenes.yaml", "entities:\n  switch.smart_plug_mini:\n    state: 'on'\n")
    _write(repo, "automations.yaml", "target:\n  entity_id: switch.smart_plug_mini\n")
    hits = scan_references(GitContext(repo), "switch.smart_plug_mini")
    assert len(hits) == 2
    paths = {h.path.as_posix() for h in hits}
    assert paths == {"scenes.yaml", "automations.yaml"}


def test_scan_respects_word_boundaries(repo):
    _write(repo, "a.yaml", "switch.smart_plug_mini_extra: 1\n")
    hits = scan_references(GitContext(repo), "switch.smart_plug_mini")
    assert hits == []


def test_scan_skips_gitignored(repo):
    (repo / ".venv").mkdir()
    _write(repo, ".venv/x.yaml", "switch.smart_plug_mini\n")
    hits = scan_references(GitContext(repo), "switch.smart_plug_mini")
    assert hits == []


def test_rewrite_replaces_all(repo):
    _write(repo, "scenes.yaml", "switch.smart_plug_mini: on\n")
    _write(repo, "auto.yaml", "entity: switch.smart_plug_mini\n")
    paths = rewrite_references(
        GitContext(repo), "switch.smart_plug_mini", "switch.smart_plug_tv",
    )
    assert (repo / "scenes.yaml").read_text() == "switch.smart_plug_tv: on\n"
    assert (repo / "auto.yaml").read_text() == "entity: switch.smart_plug_tv\n"
    assert len(paths) == 2


def test_rewrite_rolls_back_on_error(repo, monkeypatch):
    _write(repo, "a.yaml", "switch.smart_plug_mini\n")
    (repo / "a.yaml").chmod(0o444)
    try:
        with pytest.raises(PermissionError):
            rewrite_references(
                GitContext(repo), "switch.smart_plug_mini", "switch.smart_plug_tv",
            )
    finally:
        (repo / "a.yaml").chmod(0o644)
