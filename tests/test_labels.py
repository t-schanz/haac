import pytest
import yaml
from unittest.mock import AsyncMock

from haac.providers.labels import LabelsProvider


def test_diff_creates_missing():
    p = LabelsProvider()
    desired = [{"id": "urgent", "name": "Urgent", "icon": "mdi:alert", "color": "red"}]
    current = []
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert result.changes[0].action == "create"
    assert result.changes[0].name == "Urgent"


def test_diff_matches_by_name():
    p = LabelsProvider()
    desired = [{"id": "urgent", "name": "Urgent", "icon": "mdi:alert", "color": "red"}]
    current = [{"label_id": "urgent", "name": "Urgent", "icon": "mdi:alert", "color": "red"}]
    result = p.diff(desired, current)
    assert len(result.changes) == 0


def test_diff_updates_color():
    p = LabelsProvider()
    desired = [{"id": "urgent", "name": "Urgent", "icon": "mdi:alert", "color": "red"}]
    current = [{"label_id": "urgent", "name": "Urgent", "icon": "mdi:alert", "color": "blue"}]
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert result.changes[0].action == "update"
    assert "color" in result.changes[0].details[0]
    assert result.changes[0].ha_id == "urgent"


def test_diff_updates_icon():
    p = LabelsProvider()
    desired = [{"id": "urgent", "name": "Urgent", "icon": "mdi:alert", "color": "red"}]
    current = [{"label_id": "urgent", "name": "Urgent", "icon": "", "color": "red"}]
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert result.changes[0].action == "update"
    assert "icon" in result.changes[0].details[0]
    assert result.changes[0].ha_id == "urgent"


def test_diff_reports_unmanaged():
    p = LabelsProvider()
    desired = []
    current = [{"label_id": "old", "name": "Old Label", "icon": "", "color": ""}]
    result = p.diff(desired, current)
    assert len(result.unmanaged) == 1
    assert result.unmanaged[0].name == "Old Label"


def test_diff_case_insensitive_match():
    p = LabelsProvider()
    desired = [{"id": "urgent", "name": "urgent", "icon": "", "color": ""}]
    current = [{"label_id": "urgent", "name": "Urgent", "icon": "", "color": ""}]
    result = p.diff(desired, current)
    assert len(result.changes) == 0


def test_diff_updates_both_icon_and_color():
    p = LabelsProvider()
    desired = [{"id": "urgent", "name": "Urgent", "icon": "mdi:alert-new", "color": "green"}]
    current = [{"label_id": "urgent", "name": "Urgent", "icon": "mdi:alert", "color": "red"}]
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert len(result.changes[0].details) == 2


def test_diff_create_data_contains_all_fields():
    p = LabelsProvider()
    desired = [{"id": "urgent", "name": "Urgent", "icon": "mdi:alert", "color": "red"}]
    result = p.diff(desired, [])
    data = result.changes[0].data
    assert data["name"] == "Urgent"
    assert data["icon"] == "mdi:alert"
    assert data["color"] == "red"


@pytest.mark.asyncio
async def test_read_desired_empty(tmp_path):
    p = LabelsProvider()
    result = await p.read_desired(tmp_path)
    assert result == []


@pytest.mark.asyncio
async def test_read_desired_parses_yaml(tmp_path):
    p = LabelsProvider()
    (tmp_path / "labels.yaml").write_text(
        "---\nlabels:\n  - id: urgent\n    name: Urgent\n    icon: mdi:alert\n    color: red\n"
    )
    result = await p.read_desired(tmp_path)
    assert len(result) == 1
    assert result[0]["name"] == "Urgent"
    assert result[0]["color"] == "red"


@pytest.mark.asyncio
async def test_write_desired_roundtrip(tmp_path):
    p = LabelsProvider()
    original = [
        {"id": "urgent", "name": "Urgent", "icon": "mdi:alert", "color": "red"},
        {"id": "info", "name": "Info", "icon": "mdi:information", "color": "blue"},
    ]
    await p.write_desired(tmp_path, original)
    loaded = await p.read_desired(tmp_path)
    assert len(loaded) == 2
    assert loaded[0]["name"] == "Urgent"
    assert loaded[1]["name"] == "Info"


@pytest.mark.asyncio
async def test_pull_adds_new_labels(tmp_path):
    p = LabelsProvider()
    client = AsyncMock()
    client.ws_command = AsyncMock(return_value=[
        {"label_id": "urgent", "name": "Urgent", "icon": "mdi:alert", "color": "red"},
        {"label_id": "info", "name": "Info", "icon": "mdi:information", "color": "blue"},
    ])
    new_names = await p.pull(tmp_path, client)
    assert len(new_names) == 2


@pytest.mark.asyncio
async def test_pull_skips_existing(tmp_path):
    p = LabelsProvider()
    (tmp_path / "labels.yaml").write_text(
        "---\nlabels:\n  - id: urgent\n    name: Urgent\n    icon: mdi:alert\n    color: red\n"
    )
    client = AsyncMock()
    client.ws_command = AsyncMock(return_value=[
        {"label_id": "urgent", "name": "Urgent", "icon": "mdi:alert", "color": "red"},
        {"label_id": "info", "name": "Info", "icon": "mdi:information", "color": "blue"},
    ])
    new_names = await p.pull(tmp_path, client)
    assert new_names == ["Info"]
