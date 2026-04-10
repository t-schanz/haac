import pytest
from unittest.mock import AsyncMock

from haac.providers.devices import DevicesProvider


def test_diff_assigns_unassigned():
    p = DevicesProvider()
    desired = [{"match": "Wohnzimmer*", "area": "living_room"}]
    current = [{"id": "dev1", "name_by_user": None, "name": "Wohnzimmer Lampe", "area_id": None}]
    result = p.diff(desired, current, context={
        "areas": [{"area_id": "wohnzimmer", "name": "Wohnzimmer"}],
        "desired_areas": [{"id": "living_room", "name": "Wohnzimmer", "floor": "ground", "icon": ""}],
    })
    assert len(result.changes) == 1
    assert result.changes[0].action == "update"
    assert result.changes[0].data["area_id"] == "wohnzimmer"


def test_diff_skips_correctly_assigned():
    p = DevicesProvider()
    desired = [{"match": "Wohnzimmer*", "area": "living_room"}]
    current = [{"id": "dev1", "name_by_user": None, "name": "Wohnzimmer Lampe", "area_id": "wohnzimmer"}]
    result = p.diff(desired, current, context={
        "areas": [{"area_id": "wohnzimmer", "name": "Wohnzimmer"}],
        "desired_areas": [{"id": "living_room", "name": "Wohnzimmer", "floor": "ground", "icon": ""}],
    })
    assert len(result.changes) == 0


def test_diff_last_match_wins():
    p = DevicesProvider()
    desired = [
        {"match": "Wohnzimmer*", "area": "living_room"},
        {"match": "Wohnzimmer Lampe", "area": "kitchen"},
    ]
    current = [{"id": "dev1", "name_by_user": None, "name": "Wohnzimmer Lampe", "area_id": None}]
    result = p.diff(desired, current, context={
        "areas": [
            {"area_id": "wohnzimmer", "name": "Wohnzimmer"},
            {"area_id": "kuche", "name": "Küche"},
        ],
        "desired_areas": [
            {"id": "living_room", "name": "Wohnzimmer", "floor": "ground", "icon": ""},
            {"id": "kitchen", "name": "Küche", "floor": "ground", "icon": ""},
        ],
    })
    assert len(result.changes) == 1
    assert result.changes[0].data["area_id"] == "kuche"


def test_diff_uses_name_by_user_when_set():
    """name_by_user takes precedence over name for matching."""
    p = DevicesProvider()
    desired = [{"match": "Custom*", "area": "living_room"}]
    current = [{"id": "dev1", "name_by_user": "Custom Lamp", "name": "Manufacturer Name", "area_id": None}]
    result = p.diff(desired, current, context={
        "areas": [{"area_id": "wohnzimmer", "name": "Wohnzimmer"}],
        "desired_areas": [{"id": "living_room", "name": "Wohnzimmer", "floor": "ground", "icon": ""}],
    })
    assert len(result.changes) == 1


def test_diff_unmatched_device_with_area_is_unmanaged():
    p = DevicesProvider()
    desired = [{"match": "Kitchen*", "area": "kitchen"}]
    current = [{"id": "dev1", "name_by_user": None, "name": "Bedroom Light", "area_id": "bedroom"}]
    result = p.diff(desired, current, context={
        "areas": [{"area_id": "bedroom", "name": "Bedroom"}],
        "desired_areas": [{"id": "kitchen", "name": "Kitchen", "floor": "ground", "icon": ""}],
    })
    assert len(result.unmanaged) == 1
    assert "Bedroom Light" in result.unmanaged[0].name


def test_diff_unmatched_device_without_area_not_reported():
    """Devices with no area and no matching rule are silently ignored."""
    p = DevicesProvider()
    desired = [{"match": "Kitchen*", "area": "kitchen"}]
    current = [{"id": "dev1", "name_by_user": None, "name": "Random Device", "area_id": None}]
    result = p.diff(desired, current, context={
        "areas": [],
        "desired_areas": [{"id": "kitchen", "name": "Kitchen", "floor": "ground", "icon": ""}],
    })
    assert len(result.unmanaged) == 0
    assert len(result.changes) == 0


def test_diff_glob_pattern_matching():
    p = DevicesProvider()
    desired = [{"match": "*Lampe*", "area": "living_room"}]
    current = [
        {"id": "dev1", "name_by_user": None, "name": "Wohnzimmer Lampe 1", "area_id": None},
        {"id": "dev2", "name_by_user": None, "name": "Küche Lampe", "area_id": None},
        {"id": "dev3", "name_by_user": None, "name": "Ventilator", "area_id": None},
    ]
    result = p.diff(desired, current, context={
        "areas": [{"area_id": "wohnzimmer", "name": "Wohnzimmer"}],
        "desired_areas": [{"id": "living_room", "name": "Wohnzimmer", "floor": "ground", "icon": ""}],
    })
    assert len(result.changes) == 2  # dev1 and dev2 match


def test_resolve_area_id_missing_area():
    p = DevicesProvider()
    result = p._resolve_area_id("nonexistent", [], [])
    assert result is None


def test_resolve_area_id_happy_path():
    p = DevicesProvider()
    result = p._resolve_area_id(
        "living_room",
        [{"id": "living_room", "name": "Wohnzimmer"}],
        [{"area_id": "wohnzimmer", "name": "Wohnzimmer"}],
    )
    assert result == "wohnzimmer"


@pytest.mark.asyncio
async def test_read_desired_empty(tmp_path):
    p = DevicesProvider()
    result = await p.read_desired(tmp_path)
    assert result == []


@pytest.mark.asyncio
async def test_read_desired_parses_yaml(tmp_path):
    p = DevicesProvider()
    (tmp_path / "assignments.yaml").write_text(
        "---\ndevices:\n  - match: \"Wohnzimmer*\"\n    area: living_room\n"
    )
    result = await p.read_desired(tmp_path)
    assert len(result) == 1
    assert result[0]["match"] == "Wohnzimmer*"
    assert result[0]["area"] == "living_room"


@pytest.mark.asyncio
async def test_write_desired_is_noop(tmp_path):
    """Device assignments are manual glob patterns; write_desired should be a no-op."""
    p = DevicesProvider()
    await p.write_desired(tmp_path, [{"match": "x", "area": "y"}])
    assert not (tmp_path / "assignments.yaml").exists()


@pytest.mark.asyncio
async def test_pull_is_noop(tmp_path):
    """Devices pull should be a no-op (glob patterns can't be auto-generated)."""
    p = DevicesProvider()
    client = AsyncMock()
    new_names = await p.pull(tmp_path, client)
    assert new_names == []
