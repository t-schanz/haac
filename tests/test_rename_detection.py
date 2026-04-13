"""Tests for rename detection across providers."""
import subprocess
from pathlib import Path

import pytest

from haac.git_ctx import GitContext
from haac.models import Change, PlanResult, ProviderResult
from haac.output import print_plan


def test_print_plan_renders_rename(capsys):
    plan = PlanResult()
    r = ProviderResult(provider_name="entities")
    r.changes.append(Change(
        action="rename",
        resource_type="entity",
        name="switch.smart_plug_mini → switch.smart_plug_tv",
        details=[],
        data={"new_entity_id": "switch.smart_plug_tv"},
        ha_id="switch.smart_plug_mini",
    ))
    plan.results.append(r)
    print_plan(plan)
    out = capsys.readouterr().out
    assert "rename" in out.lower()
    assert "switch.smart_plug_mini" in out
    assert "switch.smart_plug_tv" in out


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    return tmp_path


def _commit_file(repo: Path, rel: str, content: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    subprocess.run(["git", "-C", str(repo), "add", rel], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "x"], check=True)


def test_floors_rename_detected(git_repo):
    from haac.providers.floors import FloorsProvider

    state = git_repo / "state"
    state.mkdir()
    yaml_content = """---
floors:
  - haac_id: f-abc
    name: Ground
    icon: ''
"""
    _commit_file(git_repo, "state/floors.yaml", yaml_content)

    # User edits name to "Ground Floor"
    (state / "floors.yaml").write_text("""---
floors:
  - haac_id: f-abc
    name: Ground Floor
    icon: ''
""")

    provider = FloorsProvider()
    desired = [{"haac_id": "f-abc", "name": "Ground Floor", "icon": ""}]
    current = [{"floor_id": "ha-123", "name": "Ground", "icon": ""}]
    ctx = {"git_ctx": GitContext(git_repo), "state_dir": state}
    result = provider.diff(desired, current, ctx)

    assert len(result.changes) == 1
    c = result.changes[0]
    assert c.action == "rename"
    assert "Ground" in c.name
    assert "Ground Floor" in c.name
    assert c.ha_id == "ha-123"
    assert c.data.get("name") == "Ground Floor"
