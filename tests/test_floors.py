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
