from haac.providers.devices import DevicesProvider


def test_diff_assigns_unassigned():
    p = DevicesProvider()
    desired = [{"match": "Wohnzimmer*", "area": "living_room"}]
    current = [{"id": "dev1", "name_by_user": None, "name": "Wohnzimmer Lampe", "area_id": None}]
    result = p.diff(desired, current, context={
        "areas": [{"area_id": "wohnzimmer", "name": "Wohnzimmer"}],
        "desired_areas": [{"id": "living_room", "name": "Wohnzimmer", "floor": "ground", "icon": ""}],
    })
    assert len(result.changes) == 1
    assert result.changes[0].action == "update"
    assert result.changes[0].data["area_id"] == "wohnzimmer"


def test_diff_skips_correctly_assigned():
    p = DevicesProvider()
    desired = [{"match": "Wohnzimmer*", "area": "living_room"}]
    current = [{"id": "dev1", "name_by_user": None, "name": "Wohnzimmer Lampe", "area_id": "wohnzimmer"}]
    result = p.diff(desired, current, context={
        "areas": [{"area_id": "wohnzimmer", "name": "Wohnzimmer"}],
        "desired_areas": [{"id": "living_room", "name": "Wohnzimmer", "floor": "ground", "icon": ""}],
    })
    assert len(result.changes) == 0


def test_diff_last_match_wins():
    p = DevicesProvider()
    desired = [
        {"match": "Wohnzimmer*", "area": "living_room"},
        {"match": "Wohnzimmer Lampe", "area": "kitchen"},
    ]
    current = [{"id": "dev1", "name_by_user": None, "name": "Wohnzimmer Lampe", "area_id": None}]
    result = p.diff(desired, current, context={
        "areas": [
            {"area_id": "wohnzimmer", "name": "Wohnzimmer"},
            {"area_id": "kuche", "name": "Küche"},
        ],
        "desired_areas": [
            {"id": "living_room", "name": "Wohnzimmer", "floor": "ground", "icon": ""},
            {"id": "kitchen", "name": "Küche", "floor": "ground", "icon": ""},
        ],
    })
    assert len(result.changes) == 1
    assert result.changes[0].data["area_id"] == "kuche"
