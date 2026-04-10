from haac.providers.helpers import HelpersProvider


def test_diff_creates_new():
    p = HelpersProvider()
    desired = [{"id": "washing_machine_running", "name": "Washing Machine Running", "icon": "mdi:washing-machine"}]
    current = []
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert result.changes[0].action == "create"
    assert result.changes[0].name == "Washing Machine Running"


def test_diff_matches_by_name():
    p = HelpersProvider()
    # HA's auto-generated ID differs from ours, but names match — should be no change
    desired = [{"id": "washing_machine_running", "name": "Washing Machine Running", "icon": "mdi:washing-machine"}]
    current = [{"id": "waschmaschine_lauft", "name": "Washing Machine Running", "icon": "mdi:washing-machine"}]
    result = p.diff(desired, current)
    assert len(result.changes) == 0


def test_diff_matches_by_name_case_insensitive():
    p = HelpersProvider()
    desired = [{"id": "my_helper", "name": "My Helper", "icon": ""}]
    current = [{"id": "my_helper_ha", "name": "my helper", "icon": ""}]
    result = p.diff(desired, current)
    assert len(result.changes) == 0


def test_diff_updates_uses_ha_id():
    p = HelpersProvider()
    # HA has a different ID but same name; update should carry HA's actual ID
    desired = [{"id": "washing_machine_running", "name": "Washing Machine Running", "icon": "mdi:washing-machine-alert"}]
    current = [{"id": "waschmaschine_lauft", "name": "Washing Machine Running", "icon": "mdi:washing-machine"}]
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert result.changes[0].action == "update"
    assert result.changes[0].ha_id == "waschmaschine_lauft"
    assert "icon" in result.changes[0].details[0]


def test_diff_updates_icon():
    p = HelpersProvider()
    desired = [{"id": "dishwasher", "name": "Dishwasher Running", "icon": "mdi:dishwasher"}]
    current = [{"id": "dishwasher", "name": "Dishwasher Running", "icon": "mdi:help"}]
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert result.changes[0].action == "update"
    assert "icon" in result.changes[0].details[0]


def test_diff_reports_unmanaged():
    p = HelpersProvider()
    desired = []
    current = [{"id": "old_helper", "name": "Old Helper", "icon": ""}]
    result = p.diff(desired, current)
    assert len(result.unmanaged) == 1
    assert result.unmanaged[0].ha_id == "old_helper"
    assert result.unmanaged[0].name == "Old Helper"
