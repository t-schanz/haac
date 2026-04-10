from haac.providers.helpers import HelpersProvider


def test_diff_creates_new():
    p = HelpersProvider()
    desired = [{"id": "washing_machine_running", "name": "Washing Machine Running", "icon": "mdi:washing-machine"}]
    current = []
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert result.changes[0].action == "create"
    assert result.changes[0].name == "Washing Machine Running"


def test_diff_matches_by_id():
    p = HelpersProvider()
    helper = {"id": "washing_machine_running", "name": "Washing Machine Running", "icon": "mdi:washing-machine"}
    result = p.diff([helper], [helper])
    assert len(result.changes) == 0


def test_diff_updates_name_and_icon():
    p = HelpersProvider()
    desired = [{"id": "dishwasher", "name": "Dishwasher Running", "icon": "mdi:dishwasher"}]
    current = [{"id": "dishwasher", "name": "Dishwasher", "icon": "mdi:help"}]
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert result.changes[0].action == "update"
    details_text = " ".join(result.changes[0].details)
    assert "name" in details_text
    assert "icon" in details_text


def test_diff_reports_unmanaged():
    p = HelpersProvider()
    desired = []
    current = [{"id": "old_helper", "name": "Old Helper", "icon": ""}]
    result = p.diff(desired, current)
    assert len(result.unmanaged) == 1
    assert result.unmanaged[0].ha_id == "old_helper"
    assert result.unmanaged[0].name == "Old Helper"
