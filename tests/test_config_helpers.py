import pytest
from unittest.mock import AsyncMock

from haac.providers.config_helpers import ConfigHelpersProvider, _fill, _suggested

SCHEMA = [
    {"name": "entity_id", "selector": {"entity": {"read_only": True}}, "description": {"suggested_value": "sensor.x"}},
    {"name": "state", "selector": {"template": {}}, "description": {"suggested_value": "{{ 1 }}"}},
    {"name": "cycle", "selector": {"select": {}}, "default": "daily"},
    {"type": "expandable", "name": "additional_options",
     "schema": [{"name": "availability", "selector": {"template": {}}, "description": {"suggested_value": "{{ true }}"}}]},
]


def test_fill_skips_read_only_and_nests_expandables():
    values = {"entity_id": "sensor.y", "state": "{{ 2 }}", "availability": "{{ false }}", "unrelated": 1}
    assert _fill(SCHEMA, values) == {"state": "{{ 2 }}", "additional_options": {"availability": "{{ false }}"}}


def test_suggested_flattens_current_values():
    assert _suggested(SCHEMA) == {"entity_id": "sensor.x", "state": "{{ 1 }}", "cycle": "daily", "availability": "{{ true }}"}


def test_diff_create_update_unmanaged():
    p = ConfigHelpersProvider()
    desired = [
        {"domain": "template", "name": "Neu", "options": {"state": "1"}},
        {"domain": "template", "name": "Alt", "options": {"state": "2", "not_in_options_flow": "x"}},
    ]
    current = [
        {"entry_id": "a", "domain": "template", "title": "alt", "options": {"state": "1"}},
        {"entry_id": "b", "domain": "history_stats", "title": "Fremd", "options": {}},
    ]
    r = p.diff(desired, current)
    assert [(c.action, c.ha_id) for c in r.changes] == [("create", None), ("update", "a")]
    assert r.changes[1].details == ["state: '1' → '2'"]
    assert [u.ha_id for u in r.unmanaged] == ["b"]


@pytest.mark.asyncio
async def test_create_walks_menu_then_form():
    client = AsyncMock()
    client.rest_post.side_effect = [
        {"type": "menu", "flow_id": "f"},
        {"type": "form", "flow_id": "f", "data_schema": [{"name": "name", "selector": {"text": {}}}, {"name": "state", "selector": {"template": {}}}]},
        {"type": "create_entry"},
    ]
    p = ConfigHelpersProvider()
    from haac.models import Change
    await p.apply_change(client, Change(action="create", resource_type="config_helper", name="x",
                                        data={"domain": "template", "menu": "sensor", "name": "X", "options": {"state": "1"}}))
    assert client.rest_post.call_args_list[1].args == ("config/config_entries/flow/f", {"next_step_id": "sensor"})
    assert client.rest_post.call_args_list[2].args == ("config/config_entries/flow/f", {"name": "X", "state": "1"})


@pytest.mark.asyncio
async def test_flow_errors_abort_and_raise():
    client = AsyncMock()
    client.rest_post.return_value = {"type": "form", "flow_id": "f", "step_id": "user", "errors": {"base": "bad"}}
    p = ConfigHelpersProvider()
    from haac.models import Change
    with pytest.raises(RuntimeError, match="bad"):
        await p.apply_change(client, Change(action="create", resource_type="config_helper", name="x",
                                            data={"domain": "template", "name": "X"}))
    client.rest_delete.assert_called_once_with("config/config_entries/flow/f")
