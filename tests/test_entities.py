import pytest
import yaml
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from haac.providers.entities import EntitiesProvider


def test_diff_updates_name():
    p = EntitiesProvider()
    desired = [{"entity_id": "light.lamp", "friendly_name": "Wohnzimmer Lampe", "icon": ""}]
    current = [{"entity_id": "light.lamp", "name": None, "icon": None}]
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert result.changes[0].action == "update"
    assert "name" in result.changes[0].details[0]


def test_diff_updates_icon():
    p = EntitiesProvider()
    desired = [{"entity_id": "light.lamp", "friendly_name": "", "icon": "mdi:lamp"}]
    current = [{"entity_id": "light.lamp", "name": None, "icon": None}]
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert "icon" in result.changes[0].details[0]


def test_diff_skips_matching():
    p = EntitiesProvider()
    desired = [{"entity_id": "light.lamp", "friendly_name": "Lampe", "icon": "mdi:lamp"}]
    current = [{"entity_id": "light.lamp", "name": "Lampe", "icon": "mdi:lamp"}]
    result = p.diff(desired, current)
    assert len(result.changes) == 0


def test_diff_skips_unknown_entity():
    p = EntitiesProvider()
    desired = [{"entity_id": "light.nonexistent", "friendly_name": "Test", "icon": ""}]
    current = []
    result = p.diff(desired, current)
    assert len(result.changes) == 0


def test_diff_updates_both_name_and_icon():
    p = EntitiesProvider()
    desired = [{"entity_id": "light.lamp", "friendly_name": "New Name", "icon": "mdi:new"}]
    current = [{"entity_id": "light.lamp", "name": "Old Name", "icon": "mdi:old"}]
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert len(result.changes[0].details) == 2
    assert "name" in result.changes[0].details[0]
    assert "icon" in result.changes[0].details[1]


def test_diff_change_data_uses_ha_field_names():
    """apply_change sends 'name' not 'friendly_name' to HA."""
    p = EntitiesProvider()
    desired = [{"entity_id": "light.lamp", "friendly_name": "My Lamp", "icon": "mdi:lamp"}]
    current = [{"entity_id": "light.lamp", "name": None, "icon": None}]
    result = p.diff(desired, current)
    assert result.changes[0].data["name"] == "My Lamp"
    assert result.changes[0].data["icon"] == "mdi:lamp"
    assert result.changes[0].data["entity_id"] == "light.lamp"


def test_diff_multiple_entities():
    p = EntitiesProvider()
    desired = [
        {"entity_id": "light.lamp", "friendly_name": "Lamp", "icon": ""},
        {"entity_id": "switch.fan", "friendly_name": "Fan", "icon": "mdi:fan"},
    ]
    current = [
        {"entity_id": "light.lamp", "name": None, "icon": None},
        {"entity_id": "switch.fan", "name": "Fan", "icon": "mdi:fan"},
    ]
    result = p.diff(desired, current)
    # Only light.lamp needs update (name change); switch.fan matches
    assert len(result.changes) == 1
    assert result.changes[0].data["entity_id"] == "light.lamp"


@pytest.mark.asyncio
async def test_read_desired_empty_file(tmp_path):
    p = EntitiesProvider()
    result = await p.read_desired(tmp_path)
    assert result == []


@pytest.mark.asyncio
async def test_read_desired_parses_yaml(tmp_path):
    p = EntitiesProvider()
    state_dir = tmp_path
    (state_dir / "entities.yaml").write_text(
        "---\nentities:\n  - entity_id: light.lamp\n    friendly_name: Lamp\n    icon: mdi:lamp\n"
    )
    result = await p.read_desired(state_dir)
    assert len(result) == 1
    assert result[0]["entity_id"] == "light.lamp"
    assert result[0]["friendly_name"] == "Lamp"
    assert result[0]["icon"] == "mdi:lamp"


@pytest.mark.asyncio
async def test_write_desired_converts_ha_format(tmp_path):
    """write_desired should convert HA registry format to haac format."""
    p = EntitiesProvider()
    ha_entities = [
        {
            "entity_id": "light.lamp",
            "name": "My Lamp",
            "icon": "mdi:lamp",
            "platform": "hue",
            "device_id": "abc123",
            "area_id": "living_room",
        },
        {
            "entity_id": "switch.fan",
            "name": "Ceiling Fan",
            "icon": "",
            "platform": "mqtt",
        },
    ]
    await p.write_desired(tmp_path, ha_entities)
    content = (tmp_path / "entities.yaml").read_text()
    data = yaml.safe_load(content)
    entities = data["entities"]
    assert len(entities) == 2
    # Should have haac format keys, not HA registry keys
    assert entities[0]["entity_id"] == "light.lamp"
    assert entities[0]["friendly_name"] == "My Lamp"
    assert entities[0]["icon"] == "mdi:lamp"
    # Should NOT have HA-only fields
    assert "platform" not in entities[0]
    assert "device_id" not in entities[0]
    assert "area_id" not in entities[0]
    # Second entity: no icon, so icon key should be absent
    assert entities[1]["entity_id"] == "switch.fan"
    assert entities[1]["friendly_name"] == "Ceiling Fan"
    assert "icon" not in entities[1]


@pytest.mark.asyncio
async def test_write_desired_skips_entities_without_customization(tmp_path):
    """Entities with no name and no icon should be excluded."""
    p = EntitiesProvider()
    ha_entities = [
        {"entity_id": "light.lamp", "name": "My Lamp", "icon": "mdi:lamp"},
        {"entity_id": "sensor.temp", "name": None, "icon": None},
        {"entity_id": "sensor.humidity", "name": "", "icon": ""},
    ]
    await p.write_desired(tmp_path, ha_entities)
    data = yaml.safe_load((tmp_path / "entities.yaml").read_text())
    assert len(data["entities"]) == 1
    assert data["entities"][0]["entity_id"] == "light.lamp"


@pytest.mark.asyncio
async def test_write_desired_noop_when_all_empty(tmp_path):
    """If all entities lack customization, don't write a file."""
    p = EntitiesProvider()
    await p.write_desired(tmp_path, [
        {"entity_id": "sensor.temp", "name": None, "icon": None},
    ])
    assert not (tmp_path / "entities.yaml").exists()


@pytest.mark.asyncio
async def test_write_desired_preserves_friendly_name_key(tmp_path):
    """Entities already in haac format (with friendly_name) should pass through."""
    p = EntitiesProvider()
    haac_entities = [
        {"entity_id": "light.lamp", "friendly_name": "My Lamp", "icon": "mdi:lamp"},
    ]
    await p.write_desired(tmp_path, haac_entities)
    data = yaml.safe_load((tmp_path / "entities.yaml").read_text())
    assert data["entities"][0]["friendly_name"] == "My Lamp"


@pytest.mark.asyncio
async def test_write_desired_starts_with_yaml_header(tmp_path):
    p = EntitiesProvider()
    await p.write_desired(tmp_path, [
        {"entity_id": "light.lamp", "friendly_name": "Lamp", "icon": ""},
    ])
    content = (tmp_path / "entities.yaml").read_text()
    assert content.startswith("---\n")


@pytest.mark.asyncio
async def test_pull_adds_new_customized_entities(tmp_path):
    """Pull should add entities with name/icon that aren't already in desired."""
    p = EntitiesProvider()
    client = AsyncMock()
    client.ws_command = AsyncMock(return_value=[
        {"entity_id": "light.lamp", "name": "My Lamp", "icon": "mdi:lamp"},
        {"entity_id": "sensor.temp", "name": "", "icon": ""},  # no customization
        {"entity_id": "switch.fan", "name": "Fan", "icon": "mdi:fan"},
    ])
    new_names = await p.pull(tmp_path, client)
    assert set(new_names) == {"light.lamp", "switch.fan"}
    # File should exist with converted format
    data = yaml.safe_load((tmp_path / "entities.yaml").read_text())
    assert len(data["entities"]) == 2


@pytest.mark.asyncio
async def test_pull_skips_already_desired(tmp_path):
    """Pull should not duplicate entities already in the desired state file."""
    p = EntitiesProvider()
    (tmp_path / "entities.yaml").write_text(
        "---\nentities:\n  - entity_id: light.lamp\n    friendly_name: Lamp\n"
    )
    client = AsyncMock()
    client.ws_command = AsyncMock(return_value=[
        {"entity_id": "light.lamp", "name": "Lamp", "icon": "mdi:lamp"},
        {"entity_id": "switch.fan", "name": "Fan", "icon": "mdi:fan"},
    ])
    new_names = await p.pull(tmp_path, client)
    assert new_names == ["switch.fan"]
    data = yaml.safe_load((tmp_path / "entities.yaml").read_text())
    assert len(data["entities"]) == 2


@pytest.mark.asyncio
async def test_pull_returns_empty_when_no_new(tmp_path):
    """Pull returns empty list when all customized entities are already in desired."""
    p = EntitiesProvider()
    (tmp_path / "entities.yaml").write_text(
        "---\nentities:\n  - entity_id: light.lamp\n    friendly_name: Lamp\n"
    )
    client = AsyncMock()
    client.ws_command = AsyncMock(return_value=[
        {"entity_id": "light.lamp", "name": "Lamp", "icon": ""},
        {"entity_id": "sensor.temp", "name": "", "icon": ""},
    ])
    new_names = await p.pull(tmp_path, client)
    assert new_names == []


@pytest.mark.asyncio
async def test_write_desired_roundtrip(tmp_path):
    """write_desired output should be readable by read_desired."""
    p = EntitiesProvider()
    original = [
        {"entity_id": "light.lamp", "friendly_name": "My Lamp", "icon": "mdi:lamp"},
        {"entity_id": "switch.fan", "friendly_name": "Fan", "icon": "mdi:fan"},
    ]
    await p.write_desired(tmp_path, original)
    loaded = await p.read_desired(tmp_path)
    assert len(loaded) == 2
    assert loaded[0]["entity_id"] == "light.lamp"
    assert loaded[0]["friendly_name"] == "My Lamp"
    assert loaded[0]["icon"] == "mdi:lamp"
    assert loaded[1]["entity_id"] == "switch.fan"
