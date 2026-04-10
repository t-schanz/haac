from haac.providers.areas import AreasProvider


def test_diff_creates_missing():
    p = AreasProvider()
    desired = [{"id": "kitchen", "name": "Küche", "floor": "ground", "icon": "mdi:stove"}]
    result = p.diff(desired, [], context={"floors": []})
    assert len(result.changes) == 1
    assert result.changes[0].action == "create"


def test_diff_matches_by_name():
    p = AreasProvider()
    desired = [{"id": "kitchen", "name": "Küche", "floor": "ground", "icon": "mdi:stove"}]
    current = [{"area_id": "kuche", "name": "Küche", "icon": "mdi:stove", "floor_id": "erdgeschoss"}]
    floors = [{"floor_id": "erdgeschoss", "name": "Erdgeschoss"}]
    # floor resolves: our "ground" → desired floor name → ... but we need desired floors too
    # Actually context has current floors from HA. We need desired floors to resolve our ID → name
    result = p.diff(desired, current, context={
        "floors": floors,
        "desired_floors": [{"id": "ground", "name": "Erdgeschoss", "icon": ""}],
    })
    assert len(result.changes) == 0


def test_diff_updates_floor():
    p = AreasProvider()
    desired = [{"id": "kitchen", "name": "Küche", "floor": "upper", "icon": "mdi:stove"}]
    current = [{"area_id": "kuche", "name": "Küche", "icon": "mdi:stove", "floor_id": "eg"}]
    result = p.diff(desired, current, context={
        "floors": [{"floor_id": "eg", "name": "EG"}, {"floor_id": "obergeschoss", "name": "Obergeschoss"}],
        "desired_floors": [{"id": "upper", "name": "Obergeschoss", "icon": ""}],
    })
    assert len(result.changes) == 1
    assert result.changes[0].action == "update"
    assert "floor" in result.changes[0].details[0]


def test_diff_reports_unmanaged():
    p = AreasProvider()
    desired = []
    current = [{"area_id": "garage", "name": "Garage", "icon": "", "floor_id": ""}]
    result = p.diff(desired, current, context={"floors": []})
    assert len(result.unmanaged) == 1
