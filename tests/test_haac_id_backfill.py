"""Tests for haac_id backfill and identity helpers."""
import re
import uuid

from haac.providers import _ensure_haac_id


UUID_RE = re.compile(r"^[0-9a-f-]{36}$")


def test_ensure_haac_id_adds_when_missing():
    entries = [{"name": "Ground"}]
    _ensure_haac_id(entries)
    assert "haac_id" in entries[0]
    assert UUID_RE.match(entries[0]["haac_id"])


def test_ensure_haac_id_preserves_existing():
    existing = str(uuid.uuid4())
    entries = [{"haac_id": existing, "name": "Ground"}]
    _ensure_haac_id(entries)
    assert entries[0]["haac_id"] == existing


def test_ensure_haac_id_assigns_unique_ids():
    entries = [{"name": "A"}, {"name": "B"}, {"name": "C"}]
    _ensure_haac_id(entries)
    ids = {e["haac_id"] for e in entries}
    assert len(ids) == 3


def test_ensure_haac_id_moves_field_to_front():
    entries = [{"name": "A", "icon": "x"}]
    _ensure_haac_id(entries)
    assert list(entries[0].keys())[0] == "haac_id"


import subprocess
from pathlib import Path

import pytest

from haac.git_ctx import GitContext
from haac.providers import git_head_entry


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    return tmp_path


def _commit_yaml(repo: Path, rel: str, content: str) -> None:
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(content)
    subprocess.run(["git", "add", rel], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=repo, check=True)


def test_git_head_entry_finds_by_haac_id(git_repo):
    _commit_yaml(git_repo, "state/entities.yaml", """---
entities:
  - haac_id: abc
    entity_id: switch.old
    friendly_name: Old
""")
    ctx = GitContext(git_repo)
    entry = git_head_entry(ctx, Path("state/entities.yaml"), "entities", "abc")
    assert entry is not None
    assert entry["entity_id"] == "switch.old"


def test_git_head_entry_returns_none_when_missing(git_repo):
    _commit_yaml(git_repo, "state/entities.yaml", """---
entities: []
""")
    ctx = GitContext(git_repo)
    assert git_head_entry(ctx, Path("state/entities.yaml"), "entities", "abc") is None


def test_git_head_entry_returns_none_when_no_head(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    ctx = GitContext(tmp_path)
    assert git_head_entry(ctx, Path("state/entities.yaml"), "entities", "abc") is None


def test_parse_state_file_passes_through_haac_id(tmp_path):
    from haac.providers import parse_state_file
    p = tmp_path / "floors.yaml"
    p.write_text("""---
floors:
  - haac_id: abc
    name: Ground
""")
    entries = parse_state_file(p, "floors", ["name"])
    assert entries[0]["haac_id"] == "abc"
    assert entries[0]["name"] == "Ground"


from haac.providers.floors import FloorsProvider


class FakeClient:
    def __init__(self, response):
        self._response = response

    async def ws_command(self, *args, **kwargs):
        return self._response


@pytest.mark.asyncio
async def test_base_pull_backfills_haac_id(tmp_path):
    """Base Provider.pull assigns haac_id to newly pulled entries."""
    provider = FloorsProvider()
    client = FakeClient([
        {"floor_id": "f1", "name": "Ground", "icon": ""},
    ])
    await provider.pull(tmp_path, client)

    import yaml
    data = yaml.safe_load((tmp_path / "floors.yaml").read_text())
    assert len(data["floors"]) == 1
    assert UUID_RE.match(data["floors"][0]["haac_id"])


@pytest.mark.asyncio
async def test_base_pull_preserves_existing_haac_id(tmp_path):
    """Second pull of same entry preserves its haac_id."""
    existing_id = str(uuid.uuid4())
    (tmp_path / "floors.yaml").write_text(f"""---
floors:
  - haac_id: {existing_id}
    name: Ground
    icon: ''
""")
    provider = FloorsProvider()
    client = FakeClient([
        {"floor_id": "f1", "name": "Ground", "icon": ""},
    ])
    await provider.pull(tmp_path, client)

    import yaml
    data = yaml.safe_load((tmp_path / "floors.yaml").read_text())
    ground = next(f for f in data["floors"] if f["name"] == "Ground")
    assert ground["haac_id"] == existing_id
