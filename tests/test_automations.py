from haac.providers.automations import AutomationsProvider


def test_diff_creates_new():
    p = AutomationsProvider()
    desired = [{"id": "test_auto", "alias": "Test", "triggers": [], "conditions": [], "actions": []}]
    current = []
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert result.changes[0].action == "create"
    assert result.changes[0].name == "Test"


def test_diff_matches_by_id():
    p = AutomationsProvider()
    auto = {"id": "test", "alias": "Test", "triggers": [], "conditions": [], "actions": [], "description": ""}
    result = p.diff([auto], [auto])
    assert len(result.changes) == 0


def test_diff_updates_alias():
    p = AutomationsProvider()
    desired = [{"id": "test", "alias": "New Name", "triggers": [], "conditions": [], "actions": [], "description": ""}]
    current = [{"id": "test", "alias": "Old Name", "triggers": [], "conditions": [], "actions": [], "description": ""}]
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert result.changes[0].action == "update"
    assert "alias" in result.changes[0].details[0]


def test_diff_detects_trigger_change():
    p = AutomationsProvider()
    desired = [{"id": "test", "alias": "Test", "triggers": [{"trigger": "time"}], "conditions": [], "actions": [], "description": ""}]
    current = [{"id": "test", "alias": "Test", "triggers": [{"trigger": "sun"}], "conditions": [], "actions": [], "description": ""}]
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert "triggers changed" in result.changes[0].details


def test_diff_reports_unmanaged():
    p = AutomationsProvider()
    desired = []
    current = [{"id": "orphan", "alias": "Orphan Auto"}]
    result = p.diff(desired, current)
    assert len(result.unmanaged) == 1
    assert result.unmanaged[0].name == "Orphan Auto"
