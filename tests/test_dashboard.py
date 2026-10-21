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


@pytest.mark.asyncio
async def test_pull_writes_flat_config_that_reads_back(tmp_path):
    p = DashboardProvider()
    config = _make_config([{"title": "Wohnzimmer", "cards": [{"type": "light"}]}])
    client = AsyncMock()
    client.ws_command.return_value = config
    assert await p.pull(tmp_path, client) == ["Lovelace"]
    assert await p.read_desired(tmp_path) == [config]


@pytest.mark.asyncio
async def test_pull_leaves_existing_file_untouched(tmp_path):
    p = DashboardProvider()
    path = tmp_path / "dashboard.yaml"
    path.write_text("---\n# hand-written\nviews: []\n")
    client = AsyncMock()
    client.ws_command.return_value = _make_config([{"title": "Other", "cards": []}])
    assert await p.pull(tmp_path, client) == []
    assert path.read_text() == "---\n# hand-written\nviews: []\n"


@pytest.mark.asyncio
async def test_url_path_dashboard_created_with_sidebar_entry(tmp_path):
    p = DashboardProvider()
    (tmp_path / "dashboard.yaml").write_text("title: Haus\nurl_path: home-dashboard\nicon: mdi:x\nviews: []\n")
    desired = await p.read_desired(tmp_path)
    client = AsyncMock()
    client.ws_command.return_value = []  # no dashboards yet
    current = await p.read_current(client)
    change = p.diff(desired, current).changes[0]
    assert (change.action, change.ha_id) == ("create", None)

    client = AsyncMock()
    await p.apply_change(client, change)
    calls = [(c.args[0], c.kwargs) for c in client.ws_command.call_args_list]
    assert calls[0] == ("lovelace/dashboards/create", {"url_path": "home-dashboard", "mode": "storage", "title": "Haus",
                                                        "icon": "mdi:x", "show_in_sidebar": True, "require_admin": False})
    assert calls[1] == ("lovelace/config/save", {"config": {"title": "Haus", "views": []}, "url_path": "home-dashboard"})


@pytest.mark.asyncio
async def test_url_path_dashboard_in_sync_has_no_changes(tmp_path):
    p = DashboardProvider()
    (tmp_path / "dashboard.yaml").write_text("title: Haus\nurl_path: home-dashboard\nicon: mdi:x\nviews: []\n")
    desired = await p.read_desired(tmp_path)
    entry = {"id": "home_dashboard", "url_path": "home-dashboard", "title": "Haus", "icon": "mdi:x"}
    client = AsyncMock()
    client.ws_command.side_effect = [[entry], {"title": "Haus", "views": []}]
    current = await p.read_current(client)
    assert p.diff(desired, current).changes == []
    entry["title"] = "Alt"
    assert p.diff(desired, current).changes[0].ha_id == "home_dashboard"


@pytest.mark.asyncio
async def test_url_path_without_hyphen_rejected(tmp_path):
    from haac.models import HaacConfigError
    (tmp_path / "dashboard.yaml").write_text("url_path: dashboard\nviews: []\n")
    with pytest.raises(HaacConfigError, match="hyphen"):
        await DashboardProvider().read_desired(tmp_path)
