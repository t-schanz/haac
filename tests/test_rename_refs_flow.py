"""Integration: plan triggers reference rewriting via auto-answered prompts."""
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    return tmp_path


@pytest.mark.asyncio
async def test_handle_rename_refs_yes_mode_rewrites(repo):
    from haac.cli import _handle_rename_refs, _handle_rename_refs_tracked
    from haac.config import HaacConfig
    from haac.models import Change

    (repo / "scenes.yaml").write_text("switch.old\n")
    subprocess.run(["git", "-C", str(repo), "add", "scenes.yaml"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "x"], check=True)
    (repo / "scenes.yaml").write_text("switch.old: x\n")

    (repo / "state").mkdir()
    config = HaacConfig(ha_url="x", ha_token="t", state_dir=repo / "state", project_dir=repo)
    changes = [("entities", Change(
        action="rename", resource_type="entity",
        name="switch.old → switch.new",
        data={"new_entity_id": "switch.new"}, ha_id="switch.old",
    ))]

    # Bool-returning shim still works
    result = await _handle_rename_refs(config, changes, "yes")
    assert result is True

    # Rewrite already happened above; write the old text back and verify tracked version
    (repo / "scenes.yaml").write_text("switch.old: x\n")
    tracked = await _handle_rename_refs_tracked(config, changes, "yes")
    assert tracked  # non-empty set is truthy

    assert "switch.new" in (repo / "scenes.yaml").read_text()


@pytest.mark.asyncio
async def test_handle_rename_refs_no_mode_skips(repo):
    from haac.cli import _handle_rename_refs
    from haac.config import HaacConfig
    from haac.models import Change

    (repo / "scenes.yaml").write_text("switch.old\n")
    subprocess.run(["git", "-C", str(repo), "add", "scenes.yaml"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "x"], check=True)

    (repo / "state").mkdir()
    config = HaacConfig(ha_url="x", ha_token="t", state_dir=repo / "state", project_dir=repo)
    changes = [("entities", Change(
        action="rename", resource_type="entity",
        name="switch.old → switch.new",
        data={"new_entity_id": "switch.new"}, ha_id="switch.old",
    ))]
    result = await _handle_rename_refs(config, changes, "no")
    assert result is False
    assert "switch.old" in (repo / "scenes.yaml").read_text()


@pytest.mark.asyncio
async def test_handle_rename_refs_no_hits_returns_false(repo):
    from haac.cli import _handle_rename_refs
    from haac.config import HaacConfig
    from haac.models import Change

    (repo / "scenes.yaml").write_text("unrelated: content\n")
    subprocess.run(["git", "-C", str(repo), "add", "scenes.yaml"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "x"], check=True)

    (repo / "state").mkdir()
    config = HaacConfig(ha_url="x", ha_token="t", state_dir=repo / "state", project_dir=repo)
    changes = [("entities", Change(
        action="rename", resource_type="entity",
        name="switch.old → switch.new",
        data={"new_entity_id": "switch.new"}, ha_id="switch.old",
    ))]
    result = await _handle_rename_refs(config, changes, "yes")
    assert result is False


@pytest.mark.asyncio
async def test_handle_rename_refs_non_repo_returns_false(tmp_path):
    from haac.cli import _handle_rename_refs
    from haac.config import HaacConfig
    from haac.models import Change

    (tmp_path / "state").mkdir()
    config = HaacConfig(ha_url="x", ha_token="t", state_dir=tmp_path / "state", project_dir=tmp_path)
    changes = [("entities", Change(
        action="rename", resource_type="entity",
        name="switch.old → switch.new",
        data={"new_entity_id": "switch.new"}, ha_id="switch.old",
    ))]
    result = await _handle_rename_refs(config, changes, "yes")
    assert result is False
