import pytest
import yaml
from unittest.mock import AsyncMock

from haac.providers.areas import AreasProvider


def test_diff_creates_missing():
    p = AreasProvider()
    desired = [{"id": "kitchen", "name": "Küche", "floor": "ground", "icon": "mdi:stove"}]
    result = p.diff(desired, [], context={"floors": []})
    assert len(result.changes) == 1
    assert result.changes[0].action == "create"


def test_diff_matches_by_name():
    p = AreasProvider()
    desired = [{"id": "kitchen", "name": "Küche", "floor": "ground", "icon": "mdi:stove"}]
    current = [{"area_id": "kuche", "name": "Küche", "icon": "mdi:stove", "floor_id": "erdgeschoss"}]
    floors = [{"floor_id": "erdgeschoss", "name": "Erdgeschoss"}]
    result = p.diff(desired, current, context={
        "floors": floors,
        "desired_floors": [{"id": "ground", "name": "Erdgeschoss", "icon": ""}],
    })
    assert len(result.changes) == 0


def test_diff_updates_floor():
    p = AreasProvider()
    desired = [{"id": "kitchen", "name": "Küche", "floor": "upper", "icon": "mdi:stove"}]
    current = [{"area_id": "kuche", "name": "Küche", "icon": "mdi:stove", "floor_id": "eg"}]
    result = p.diff(desired, current, context={
        "floors": [{"floor_id": "eg", "name": "EG"}, {"floor_id": "obergeschoss", "name": "Obergeschoss"}],
        "desired_floors": [{"id": "upper", "name": "Obergeschoss", "icon": ""}],
    })
    assert len(result.changes) == 1
    assert result.changes[0].action == "update"
    assert "floor" in result.changes[0].details[0]


def test_diff_reports_unmanaged():
    p = AreasProvider()
    desired = []
    current = [{"area_id": "garage", "name": "Garage", "icon": "", "floor_id": ""}]
    result = p.diff(desired, current, context={"floors": []})
    assert len(result.unmanaged) == 1


def test_diff_updates_icon():
    p = AreasProvider()
    desired = [{"id": "kitchen", "name": "Küche", "floor": "ground", "icon": "mdi:stove"}]
    current = [{"area_id": "kuche", "name": "Küche", "icon": "", "floor_id": "erdgeschoss"}]
    result = p.diff(desired, current, context={
        "floors": [{"floor_id": "erdgeschoss", "name": "Erdgeschoss"}],
        "desired_floors": [{"id": "ground", "name": "Erdgeschoss", "icon": ""}],
    })
    assert len(result.changes) == 1
    assert result.changes[0].action == "update"
    assert "icon" in result.changes[0].details[0]


def test_diff_case_insensitive_name_match():
    p = AreasProvider()
    desired = [{"id": "kitchen", "name": "küche", "icon": "", "floor": None}]
    current = [{"area_id": "kuche", "name": "Küche", "icon": "", "floor_id": None}]
    result = p.diff(desired, current, context={"floors": []})
    assert len(result.changes) == 0


def test_diff_create_data_includes_floor():
    p = AreasProvider()
    desired = [{"id": "kitchen", "name": "Küche", "floor": "ground", "icon": "mdi:stove"}]
    result = p.diff(desired, [], context={
        "floors": [{"floor_id": "erdgeschoss", "name": "Erdgeschoss"}],
        "desired_floors": [{"id": "ground", "name": "Erdgeschoss", "icon": ""}],
    })
    data = result.changes[0].data
    assert data["name"] == "Küche"
    assert data["icon"] == "mdi:stove"
    assert data["floor_id"] == "erdgeschoss"


def test_diff_create_with_missing_floor():
    """If the floor doesn't exist yet, floor_id should be None."""
    p = AreasProvider()
    desired = [{"id": "kitchen", "name": "Küche", "floor": "nonexistent", "icon": ""}]
    result = p.diff(desired, [], context={"floors": [], "desired_floors": []})
    assert result.changes[0].data["floor_id"] is None


def test_diff_multiple_areas():
    p = AreasProvider()
    desired = [
        {"id": "kitchen", "name": "Küche", "floor": None, "icon": ""},
        {"id": "living", "name": "Wohnzimmer", "floor": None, "icon": ""},
    ]
    current = [
        {"area_id": "kuche", "name": "Küche", "icon": "", "floor_id": None},
    ]
    result = p.diff(desired, current, context={"floors": []})
    assert len(result.changes) == 1
    assert result.changes[0].action == "create"
    assert result.changes[0].name == "Wohnzimmer"


def test_resolve_floor_id_returns_none_for_missing():
    p = AreasProvider()
    result = p._resolve_floor_id("nonexistent", [], [])
    assert result is None


def test_resolve_floor_id_returns_none_for_none():
    p = AreasProvider()
    result = p._resolve_floor_id(None, [], [])
    assert result is None


@pytest.mark.asyncio
async def test_read_desired_empty(tmp_path):
    p = AreasProvider()
    result = await p.read_desired(tmp_path)
    assert result == []


@pytest.mark.asyncio
async def test_read_desired_parses_yaml(tmp_path):
    p = AreasProvider()
    (tmp_path / "areas.yaml").write_text(
        "---\nareas:\n  - id: kitchen\n    name: Küche\n    floor: ground\n    icon: mdi:stove\n"
    )
    result = await p.read_desired(tmp_path)
    assert len(result) == 1
    assert result[0]["name"] == "Küche"


@pytest.mark.asyncio
async def test_write_desired_roundtrip(tmp_path):
    p = AreasProvider()
    original = [
        {"id": "kitchen", "name": "Küche", "floor": "ground", "icon": "mdi:stove"},
    ]
    await p.write_desired(tmp_path, original)
    loaded = await p.read_desired(tmp_path)
    assert len(loaded) == 1
    assert loaded[0]["name"] == "Küche"


@pytest.mark.asyncio
async def test_pull_adds_new_areas(tmp_path):
    p = AreasProvider()
    client = AsyncMock()
    client.ws_command = AsyncMock(return_value=[
        {"area_id": "kuche", "name": "Küche", "icon": "mdi:stove", "floor_id": "eg"},
        {"area_id": "wohnzimmer", "name": "Wohnzimmer", "icon": "", "floor_id": None},
    ])
    new_names = await p.pull(tmp_path, client)
    assert len(new_names) == 2


@pytest.mark.asyncio
async def test_pull_skips_existing(tmp_path):
    p = AreasProvider()
    (tmp_path / "areas.yaml").write_text(
        "---\nareas:\n  - id: kitchen\n    name: Küche\n    floor: ground\n    icon: mdi:stove\n"
    )
    client = AsyncMock()
    client.ws_command = AsyncMock(return_value=[
        {"area_id": "kuche", "name": "Küche", "icon": "mdi:stove", "floor_id": "eg"},
        {"area_id": "wohnzimmer", "name": "Wohnzimmer", "icon": "", "floor_id": None},
    ])
    new_names = await p.pull(tmp_path, client)
    assert new_names == ["Wohnzimmer"]
