from haac.providers.scenes import ScenesProvider


def test_diff_creates_new():
    p = ScenesProvider()
    desired = [{"id": "morning_light", "name": "Morning Light", "entities": {}}]
    current = []
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert result.changes[0].action == "create"
    assert result.changes[0].name == "Morning Light"


def test_diff_matches_by_id():
    p = ScenesProvider()
    scene = {"id": "morning_light", "name": "Morning Light", "entities": {"light.kitchen": {"state": "on"}}}
    result = p.diff([scene], [scene])
    assert len(result.changes) == 0


def test_diff_updates_name():
    p = ScenesProvider()
    desired = [{"id": "morning_light", "name": "New Name", "entities": {}}]
    current = [{"id": "morning_light", "name": "Old Name", "entities": {}}]
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert result.changes[0].action == "update"
    assert "name" in result.changes[0].details[0]


def test_diff_updates_entities():
    p = ScenesProvider()
    desired = [{"id": "evening", "name": "Evening", "entities": {"light.living_room": {"state": "on", "brightness": 100}}}]
    current = [{"id": "evening", "name": "Evening", "entities": {"light.living_room": {"state": "on", "brightness": 200}}}]
    result = p.diff(desired, current)
    assert len(result.changes) == 1
    assert result.changes[0].action == "update"
    assert "entities changed" in result.changes[0].details


def test_diff_reports_unmanaged():
    p = ScenesProvider()
    desired = []
    current = [{"id": "orphan_scene", "name": "Orphan Scene", "entities": {}}]
    result = p.diff(desired, current)
    assert len(result.unmanaged) == 1
    assert result.unmanaged[0].name == "Orphan Scene"
