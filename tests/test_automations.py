import pytest
import yaml
from unittest.mock import AsyncMock

from haac.providers.automations import AutomationsProvider


def test_diff_creates_new():
    p = AutomationsProvider()
    desired = [{"id": "test_auto", "alias": "Test", "triggers": [], "conditions": [], "actions": []}]
    current = []
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert result.changes[0].action == "create"
    assert result.changes[0].name == "Test"


def test_diff_matches_by_id():
    p = AutomationsProvider()
    auto = {"id": "test", "alias": "Test", "triggers": [], "conditions": [], "actions": [], "description": ""}
    result = p.diff([auto], [auto])
    assert len(result.changes) == 0


def test_diff_updates_alias():
    p = AutomationsProvider()
    desired = [{"id": "test", "alias": "New Name", "triggers": [], "conditions": [], "actions": [], "description": ""}]
    current = [{"id": "test", "alias": "Old Name", "triggers": [], "conditions": [], "actions": [], "description": ""}]
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert result.changes[0].action == "update"
    assert "alias" in result.changes[0].details[0]


def test_diff_detects_trigger_change():
    p = AutomationsProvider()
    desired = [{"id": "test", "alias": "Test", "triggers": [{"trigger": "time"}], "conditions": [], "actions": [], "description": ""}]
    current = [{"id": "test", "alias": "Test", "triggers": [{"trigger": "sun"}], "conditions": [], "actions": [], "description": ""}]
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert "triggers changed" in result.changes[0].details


def test_diff_reports_unmanaged():
    p = AutomationsProvider()
    desired = []
    current = [{"id": "orphan", "alias": "Orphan Auto"}]
    result = p.diff(desired, current)
    assert len(result.unmanaged) == 1
    assert result.unmanaged[0].name == "Orphan Auto"


def test_diff_detects_condition_change():
    p = AutomationsProvider()
    desired = [{"id": "test", "alias": "Test", "triggers": [], "conditions": [{"condition": "state"}], "actions": [], "description": ""}]
    current = [{"id": "test", "alias": "Test", "triggers": [], "conditions": [], "actions": [], "description": ""}]
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert "conditions changed" in result.changes[0].details


def test_diff_detects_action_change():
    p = AutomationsProvider()
    desired = [{"id": "test", "alias": "Test", "triggers": [], "conditions": [], "actions": [{"service": "light.turn_on"}], "description": ""}]
    current = [{"id": "test", "alias": "Test", "triggers": [], "conditions": [], "actions": [{"service": "light.turn_off"}], "description": ""}]
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert "actions changed" in result.changes[0].details


def test_diff_detects_description_change():
    p = AutomationsProvider()
    desired = [{"id": "test", "alias": "Test", "triggers": [], "conditions": [], "actions": [], "description": "New desc"}]
    current = [{"id": "test", "alias": "Test", "triggers": [], "conditions": [], "actions": [], "description": "Old desc"}]
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert "description changed" in result.changes[0].details


def test_diff_multiple_changes():
    """Multiple field changes produce multiple details."""
    p = AutomationsProvider()
    desired = [{"id": "test", "alias": "New", "triggers": [{"t": 1}], "conditions": [{"c": 1}], "actions": [{"a": 1}], "description": "new"}]
    current = [{"id": "test", "alias": "Old", "triggers": [], "conditions": [], "actions": [], "description": "old"}]
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    details = result.changes[0].details
    assert len(details) == 5  # alias, triggers, conditions, actions, description


def test_diff_ignores_automations_without_id():
    """HA automations without 'id' field are excluded from matching."""
    p = AutomationsProvider()
    desired = [{"id": "test", "alias": "Test", "triggers": [], "conditions": [], "actions": [], "description": ""}]
    current = [{"alias": "No ID Auto", "triggers": []}]  # no 'id' field
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert result.changes[0].action == "create"
    # The no-id automation shouldn't appear in unmanaged either
    assert len(result.unmanaged) == 0


@pytest.mark.asyncio
async def test_read_desired_empty(tmp_path):
    p = AutomationsProvider()
    result = await p.read_desired(tmp_path)
    assert result == []


@pytest.mark.asyncio
async def test_read_desired_parses_yaml(tmp_path):
    p = AutomationsProvider()
    (tmp_path / "automations.yaml").write_text(
        "---\nautomations:\n  - id: test\n    alias: Test\n    triggers: []\n    conditions: []\n    actions: []\n"
    )
    result = await p.read_desired(tmp_path)
    assert len(result) == 1
    assert result[0]["id"] == "test"
    assert result[0]["alias"] == "Test"


@pytest.mark.asyncio
async def test_write_desired_roundtrip(tmp_path):
    p = AutomationsProvider()
    original = [
        {"id": "test", "alias": "Test Auto", "triggers": [{"trigger": "time"}], "conditions": [], "actions": []},
    ]
    await p.write_desired(tmp_path, original)
    loaded = await p.read_desired(tmp_path)
    assert len(loaded) == 1
    assert loaded[0]["alias"] == "Test Auto"


@pytest.mark.asyncio
async def test_write_desired_yaml_header(tmp_path):
    p = AutomationsProvider()
    await p.write_desired(tmp_path, [{"id": "t", "alias": "Test"}])
    content = (tmp_path / "automations.yaml").read_text()
    assert content.startswith("---\n")
