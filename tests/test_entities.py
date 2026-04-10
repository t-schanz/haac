from haac.providers.entities import EntitiesProvider


def test_diff_updates_name():
    p = EntitiesProvider()
    desired = [{"entity_id": "light.lamp", "friendly_name": "Wohnzimmer Lampe", "icon": ""}]
    current = [{"entity_id": "light.lamp", "name": None, "icon": None}]
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert result.changes[0].action == "update"
    assert "name" in result.changes[0].details[0]


def test_diff_updates_icon():
    p = EntitiesProvider()
    desired = [{"entity_id": "light.lamp", "friendly_name": "", "icon": "mdi:lamp"}]
    current = [{"entity_id": "light.lamp", "name": None, "icon": None}]
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert "icon" in result.changes[0].details[0]


def test_diff_skips_matching():
    p = EntitiesProvider()
    desired = [{"entity_id": "light.lamp", "friendly_name": "Lampe", "icon": "mdi:lamp"}]
    current = [{"entity_id": "light.lamp", "name": "Lampe", "icon": "mdi:lamp"}]
    result = p.diff(desired, current)
    assert len(result.changes) == 0


def test_diff_skips_unknown_entity():
    p = EntitiesProvider()
    desired = [{"entity_id": "light.nonexistent", "friendly_name": "Test", "icon": ""}]
    current = []
    result = p.diff(desired, current)
    assert len(result.changes) == 0
