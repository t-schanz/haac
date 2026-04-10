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
