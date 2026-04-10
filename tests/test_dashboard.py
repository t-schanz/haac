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
