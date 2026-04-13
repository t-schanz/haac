"""End-to-end test: plan picks up rename via GitContext from config."""
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def ha_repo(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    return tmp_path


def test_plan_builds_context_with_git_ctx(ha_repo):
    """_build_context puts a GitContext under 'git_ctx' and state_dir under 'state_dir'."""
    import asyncio

    from haac.cli import _build_context
    from haac.config import Config

    state = ha_repo / "state"
    state.mkdir()
    (ha_repo / "haac.yaml").write_text('ha_url: "http://x"\n')

    cfg = Config(ha_url="http://x", ha_token="t", state_dir=state, project_dir=ha_repo)

    class FakeClient:
        async def ws_command(self, *a, **k): return []
        async def rest_get(self, *a, **k): return []

    ctx = asyncio.run(_build_context([], FakeClient(), cfg))
    assert "git_ctx" in ctx
    assert "state_dir" in ctx
    assert ctx["state_dir"] == state


import asyncio
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_apply_invokes_rename_api(tmp_path):
    """apply calls provider.apply_change for rename actions — specifically entities."""
    from haac.models import Change
    from haac.providers.entities import EntitiesProvider

    provider = EntitiesProvider()
    client = AsyncMock()
    client.ws_command = AsyncMock()

    change = Change(
        action="rename",
        resource_type="entity",
        name="switch.a → switch.b",
        data={"new_entity_id": "switch.b"},
        ha_id="switch.a",
    )
    await provider.apply_change(client, change)

    client.ws_command.assert_called_once()
    args, kwargs = client.ws_command.call_args
    assert args[0] == "config/entity_registry/update"
    assert kwargs["entity_id"] == "switch.a"
    assert kwargs["new_entity_id"] == "switch.b"
