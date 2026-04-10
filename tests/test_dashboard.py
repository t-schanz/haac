import pytest
from unittest.mock import AsyncMock

from haac.providers.dashboard import DashboardProvider


def _make_config(views):
    return {"views": views}


def test_diff_detects_change():
    p = DashboardProvider()
    desired = [_make_config([{"title": "Home", "cards": [{"type": "weather-forecast"}]}])]
    current = [_make_config([])]
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert result.changes[0].action == "update"
    assert result.changes[0].name == "Lovelace"


def test_diff_skip_unchanged():
    p = DashboardProvider()
    config = _make_config([{"title": "Home", "cards": [{"type": "weather-forecast"}]}])
    result = p.diff([config], [config])
    assert len(result.changes) == 0


def test_diff_counts_views_and_cards():
    p = DashboardProvider()
    desired_config = _make_config([
        {"title": "Living Room", "cards": [{"type": "light"}, {"type": "sensor"}]},
        {"title": "Bedroom", "cards": [{"type": "light"}, {"type": "light"}, {"type": "media-player"}]},
    ])
    result = p.diff([desired_config], [])
    assert len(result.changes) == 1
    details = result.changes[0].details[0]
    assert "2 views" in details
    assert "5 cards" in details


def test_diff_no_desired_returns_empty():
    p = DashboardProvider()
    result = p.diff([], [_make_config([{"title": "Home", "cards": []}])])
    assert len(result.changes) == 0


def test_diff_empty_current():
    p = DashboardProvider()
    desired_config = _make_config([{"title": "Home", "cards": [{"type": "light"}]}])
    result = p.diff([desired_config], [])
    assert len(result.changes) == 1
    assert result.changes[0].action == "update"


def test_diff_single_view_no_cards():
    p = DashboardProvider()
    desired_config = _make_config([{"title": "Empty", "cards": []}])
    current_config = _make_config([{"title": "Home", "cards": [{"type": "light"}]}])
    result = p.diff([desired_config], [current_config])
    assert len(result.changes) == 1
    assert "1 views" in result.changes[0].details[0]
    assert "0 cards" in result.changes[0].details[0]


def test_diff_data_contains_full_config():
    p = DashboardProvider()
    desired_config = _make_config([{"title": "Home", "cards": [{"type": "light"}]}])
    result = p.diff([desired_config], [])
    assert result.changes[0].data == desired_config


@pytest.mark.asyncio
async def test_read_desired_empty(tmp_path):
    p = DashboardProvider()
    result = await p.read_desired(tmp_path)
    assert result == []


@pytest.mark.asyncio
async def test_read_desired_wraps_in_list(tmp_path):
    """read_desired wraps the YAML config in a list for consistency."""
    p = DashboardProvider()
    (tmp_path / "dashboard.yaml").write_text(
        "---\nviews:\n  - title: Home\n    cards: []\n"
    )
    result = await p.read_desired(tmp_path)
    assert len(result) == 1
    assert result[0]["views"][0]["title"] == "Home"
