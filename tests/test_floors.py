import pytest
import yaml
from unittest.mock import AsyncMock

from haac.providers.floors import FloorsProvider


def test_diff_creates_missing():
    p = FloorsProvider()
    desired = [{"id": "ground", "name": "Erdgeschoss", "icon": "mdi:home-floor-0"}]
    current = []
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert result.changes[0].action == "create"
    assert result.changes[0].name == "Erdgeschoss"


def test_diff_matches_by_name():
    p = FloorsProvider()
    desired = [{"id": "ground", "name": "Erdgeschoss", "icon": "mdi:home-floor-0"}]
    current = [{"floor_id": "erdgeschoss", "name": "Erdgeschoss", "icon": "mdi:home-floor-0"}]
    result = p.diff(desired, current)
    assert len(result.changes) == 0


def test_diff_updates_icon():
    p = FloorsProvider()
    desired = [{"id": "ground", "name": "Erdgeschoss", "icon": "mdi:home-floor-0"}]
    current = [{"floor_id": "erdgeschoss", "name": "Erdgeschoss", "icon": ""}]
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert result.changes[0].action == "update"
    assert "icon" in result.changes[0].details[0]
    assert result.changes[0].ha_id == "erdgeschoss"


def test_diff_reports_unmanaged():
    p = FloorsProvider()
    desired = []
    current = [{"floor_id": "old", "name": "Old Floor", "icon": ""}]
    result = p.diff(desired, current)
    assert len(result.unmanaged) == 1
    assert result.unmanaged[0].name == "Old Floor"


def test_diff_case_insensitive_match():
    p = FloorsProvider()
    desired = [{"id": "ground", "name": "erdgeschoss", "icon": ""}]
    current = [{"floor_id": "eg", "name": "Erdgeschoss", "icon": ""}]
    result = p.diff(desired, current)
    assert len(result.changes) == 0


def test_diff_multiple_floors():
    p = FloorsProvider()
    desired = [
        {"id": "ground", "name": "Erdgeschoss", "icon": "mdi:home-floor-0"},
        {"id": "upper", "name": "Obergeschoss", "icon": "mdi:home-floor-1"},
    ]
    current = [
        {"floor_id": "eg", "name": "Erdgeschoss", "icon": "mdi:home-floor-0"},
    ]
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert result.changes[0].action == "create"
    assert result.changes[0].name == "Obergeschoss"


def test_diff_create_data_contains_name_and_icon():
    p = FloorsProvider()
    desired = [{"id": "ground", "name": "Erdgeschoss", "icon": "mdi:home-floor-0"}]
    result = p.diff(desired, [])
    change = result.changes[0]
    assert change.data["name"] == "Erdgeschoss"
    assert change.data["icon"] == "mdi:home-floor-0"


@pytest.mark.asyncio
async def test_read_desired_empty(tmp_path):
    p = FloorsProvider()
    result = await p.read_desired(tmp_path)
    assert result == []


@pytest.mark.asyncio
async def test_read_desired_parses_yaml(tmp_path):
    p = FloorsProvider()
    (tmp_path / "floors.yaml").write_text(
        "---\nfloors:\n  - id: ground\n    name: Erdgeschoss\n    icon: mdi:home-floor-0\n"
    )
    result = await p.read_desired(tmp_path)
    assert len(result) == 1
    assert result[0]["name"] == "Erdgeschoss"


@pytest.mark.asyncio
async def test_write_desired_roundtrip(tmp_path):
    p = FloorsProvider()
    original = [
        {"id": "ground", "name": "Erdgeschoss", "icon": "mdi:home-floor-0"},
        {"id": "upper", "name": "Obergeschoss", "icon": "mdi:home-floor-1"},
    ]
    await p.write_desired(tmp_path, original)
    loaded = await p.read_desired(tmp_path)
    assert len(loaded) == 2
    assert loaded[0]["name"] == "Erdgeschoss"
    assert loaded[1]["name"] == "Obergeschoss"


@pytest.mark.asyncio
async def test_write_desired_yaml_header(tmp_path):
    p = FloorsProvider()
    await p.write_desired(tmp_path, [{"id": "g", "name": "Ground", "icon": ""}])
    content = (tmp_path / "floors.yaml").read_text()
    assert content.startswith("---\n")


@pytest.mark.asyncio
async def test_pull_adds_new_floors(tmp_path):
    p = FloorsProvider()
    client = AsyncMock()
    client.ws_command = AsyncMock(return_value=[
        {"floor_id": "eg", "name": "Erdgeschoss", "icon": "mdi:home-floor-0"},
        {"floor_id": "og", "name": "Obergeschoss", "icon": "mdi:home-floor-1"},
    ])
    new_names = await p.pull(tmp_path, client)
    assert len(new_names) == 2
    data = yaml.safe_load((tmp_path / "floors.yaml").read_text())
    assert len(data["floors"]) == 2


@pytest.mark.asyncio
async def test_pull_skips_existing(tmp_path):
    p = FloorsProvider()
    (tmp_path / "floors.yaml").write_text(
        "---\nfloors:\n  - id: ground\n    name: Erdgeschoss\n    icon: ''\n"
    )
    client = AsyncMock()
    client.ws_command = AsyncMock(return_value=[
        {"floor_id": "eg", "name": "Erdgeschoss", "icon": "mdi:home-floor-0"},
        {"floor_id": "og", "name": "Obergeschoss", "icon": "mdi:home-floor-1"},
    ])
    new_names = await p.pull(tmp_path, client)
    assert new_names == ["Obergeschoss"]


@pytest.mark.asyncio
async def test_pull_returns_empty_when_all_exist(tmp_path):
    p = FloorsProvider()
    (tmp_path / "floors.yaml").write_text(
        "---\nfloors:\n  - id: ground\n    name: Erdgeschoss\n    icon: ''\n"
    )
    client = AsyncMock()
    client.ws_command = AsyncMock(return_value=[
        {"floor_id": "eg", "name": "Erdgeschoss", "icon": ""},
    ])
    new_names = await p.pull(tmp_path, client)
    assert new_names == []


def test_has_state_file_true(tmp_path):
    p = FloorsProvider()
    (tmp_path / "floors.yaml").write_text("---\nfloors: []\n")
    assert p.has_state_file(tmp_path) is True


def test_has_state_file_false(tmp_path):
    p = FloorsProvider()
    assert p.has_state_file(tmp_path) is False
