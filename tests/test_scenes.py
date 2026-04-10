import pytest
import yaml
from unittest.mock import AsyncMock

from haac.providers.scenes import ScenesProvider


def test_diff_creates_new():
    p = ScenesProvider()
    desired = [{"id": "morning_light", "name": "Morning Light", "entities": {}}]
    current = []
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert result.changes[0].action == "create"
    assert result.changes[0].name == "Morning Light"


def test_diff_matches_by_id():
    p = ScenesProvider()
    scene = {"id": "morning_light", "name": "Morning Light", "entities": {"light.kitchen": {"state": "on"}}}
    result = p.diff([scene], [scene])
    assert len(result.changes) == 0


def test_diff_updates_name():
    p = ScenesProvider()
    desired = [{"id": "morning_light", "name": "New Name", "entities": {}}]
    current = [{"id": "morning_light", "name": "Old Name", "entities": {}}]
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert result.changes[0].action == "update"
    assert "name" in result.changes[0].details[0]


def test_diff_updates_entities():
    p = ScenesProvider()
    desired = [{"id": "evening", "name": "Evening", "entities": {"light.living_room": {"state": "on", "brightness": 100}}}]
    current = [{"id": "evening", "name": "Evening", "entities": {"light.living_room": {"state": "on", "brightness": 200}}}]
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert result.changes[0].action == "update"
    assert "entities changed" in result.changes[0].details


def test_diff_reports_unmanaged():
    p = ScenesProvider()
    desired = []
    current = [{"id": "orphan_scene", "name": "Orphan Scene", "entities": {}}]
    result = p.diff(desired, current)
    assert len(result.unmanaged) == 1
    assert result.unmanaged[0].name == "Orphan Scene"


def test_diff_detects_name_and_entity_change():
    p = ScenesProvider()
    desired = [{"id": "morning", "name": "New Morning", "entities": {"light.bed": {"state": "on"}}}]
    current = [{"id": "morning", "name": "Old Morning", "entities": {"light.bed": {"state": "off"}}}]
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert len(result.changes[0].details) == 2


def test_diff_ignores_scenes_without_id():
    """Scenes without 'id' (e.g. Hue scenes) should not appear in unmanaged."""
    p = ScenesProvider()
    desired = [{"id": "my_scene", "name": "My Scene", "entities": {}}]
    current = [{"name": "Hue Scene", "entities": {}}]  # no 'id'
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert result.changes[0].action == "create"
    assert len(result.unmanaged) == 0


def test_diff_create_data_includes_full_scene():
    p = ScenesProvider()
    desired = [{"id": "morning", "name": "Morning", "entities": {"light.bed": {"state": "on"}}}]
    result = p.diff(desired, [])
    data = result.changes[0].data
    assert data["id"] == "morning"
    assert data["name"] == "Morning"
    assert data["entities"] == {"light.bed": {"state": "on"}}


@pytest.mark.asyncio
async def test_read_desired_empty(tmp_path):
    p = ScenesProvider()
    result = await p.read_desired(tmp_path)
    assert result == []


@pytest.mark.asyncio
async def test_read_desired_parses_yaml(tmp_path):
    p = ScenesProvider()
    (tmp_path / "scenes.yaml").write_text(
        "---\nscenes:\n  - id: morning\n    name: Morning\n    entities:\n      light.bed:\n        state: 'on'\n"
    )
    result = await p.read_desired(tmp_path)
    assert len(result) == 1
    assert result[0]["id"] == "morning"
    assert result[0]["name"] == "Morning"


@pytest.mark.asyncio
async def test_write_desired_roundtrip(tmp_path):
    p = ScenesProvider()
    original = [
        {"id": "morning", "name": "Morning", "entities": {"light.bed": {"state": "on"}}},
    ]
    await p.write_desired(tmp_path, original)
    loaded = await p.read_desired(tmp_path)
    assert len(loaded) == 1
    assert loaded[0]["name"] == "Morning"
    assert loaded[0]["entities"]["light.bed"]["state"] == "on"
