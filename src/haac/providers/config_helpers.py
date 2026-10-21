"""Config-entry helpers provider — template, history_stats, utility_meter via config/options flows."""

from pathlib import Path

from haac.client import HAClient
from haac.models import Change, ProviderResult, Unmanaged
from haac.providers import Provider, parse_state_file, register

DOMAINS = ("template", "history_stats", "utility_meter")
_MAX_STEPS = 10


def _fill(schema: list[dict], values: dict) -> dict:
    """Pick the values a flow form asks for. Flat `values` also feed expandable sections."""
    out = {}
    for field in schema:
        if field.get("type") == "expandable":
            sub = _fill(field.get("schema", []), values)
            if sub:
                out[field["name"]] = sub
            continue
        selector = next(iter(field.get("selector", {}).values()), None)
        if isinstance(selector, dict) and selector.get("read_only"):
            continue
        if field["name"] in values:
            out[field["name"]] = values[field["name"]]
    return out


def _suggested(schema: list[dict]) -> dict:
    """Current values as an options flow pre-fills them, flattened."""
    out = {}
    for field in schema:
        if field.get("type") == "expandable":
            out.update(_suggested(field.get("schema", [])))
            continue
        desc = field.get("description") or {}
        if "suggested_value" in desc:
            out[field["name"]] = desc["suggested_value"]
        elif "default" in field:
            out[field["name"]] = field["default"]
    return out


def _flow_values(helper: dict) -> dict:
    return {"name": helper["name"], **(helper.get("options") or {})}


class ConfigHelpersProvider(Provider):
    name = "config_helpers"
    state_file = "config_helpers.yaml"
    depends_on = []

    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        return parse_state_file(path, "config_helpers", ["domain", "name"])

    async def read_current(self, client: HAClient) -> list[dict]:
        try:
            entries = await client.rest_get("config/config_entries/entry")
        except Exception:
            return []
        current = []
        for e in entries:
            if e["domain"] not in DOMAINS:
                continue
            options = {}
            if e.get("supports_options"):
                flow = await client.rest_post("config/config_entries/options/flow", {"handler": e["entry_id"]})
                options = _suggested(flow.get("data_schema") or [])
                await client.rest_delete(f"config/config_entries/options/flow/{flow['flow_id']}")
            current.append({"entry_id": e["entry_id"], "domain": e["domain"], "title": e["title"], "options": options})
        return current

    def diff(self, desired: list[dict], current: list[dict], context: dict | None = None) -> ProviderResult:
        result = ProviderResult(provider_name=self.name)
        by_key = {(c["domain"], c["title"].lower()): c for c in current}
        matched = set()

        for helper in desired:
            cur = by_key.get((helper["domain"], helper["name"].lower()))
            if cur is None:
                result.changes.append(Change(
                    action="create", resource_type="config_helper",
                    name=f"{helper['domain']}: {helper['name']}", data=helper,
                ))
                continue
            matched.add(cur["entry_id"])
            # ponytail: only keys the options flow exposes can change in place; others
            # (e.g. utility_meter cycle) need delete + re-create.
            details = [
                f"{k}: {cur['options'][k]!r} → {v!r}"
                for k, v in (helper.get("options") or {}).items()
                if k in cur["options"] and cur["options"][k] != v
            ]
            if details:
                result.changes.append(Change(
                    action="update", resource_type="config_helper",
                    name=f"{helper['domain']}: {helper['name']}", details=details,
                    data=helper, ha_id=cur["entry_id"],
                ))

        for cur in current:
            if cur["entry_id"] not in matched:
                result.unmanaged.append(Unmanaged(
                    resource_type="config_helper", ha_id=cur["entry_id"],
                    name=f"{cur['domain']}: {cur['title']}",
                ))
        return result

    async def _walk(self, client: HAClient, base: str, start: dict, helper: dict) -> None:
        flow = await client.rest_post(base, start)
        values = _flow_values(helper)
        for _ in range(_MAX_STEPS):
            kind = flow.get("type")
            if kind == "create_entry":
                return
            if kind == "menu":
                data = {"next_step_id": helper["menu"]}
            elif kind == "form":
                if flow.get("errors"):
                    break
                data = _fill(flow.get("data_schema") or [], values)
            else:
                break
            flow = await client.rest_post(f"{base}/{flow['flow_id']}", data)
        if flow.get("flow_id"):
            await client.rest_delete(f"{base}/{flow['flow_id']}")
        raise RuntimeError(f"{helper['name']}: flow stopped at {flow.get('step_id')} — {flow.get('errors') or flow.get('reason')}")

    async def apply_change(self, client: HAClient, change: Change) -> None:
        if change.action == "create":
            await self._walk(client, "config/config_entries/flow", {"handler": change.data["domain"]}, change.data)
        elif change.action == "update":
            await self._walk(client, "config/config_entries/options/flow", {"handler": change.ha_id}, change.data)

    async def delete(self, client: HAClient, ha_id: str) -> None:
        await client.rest_delete(f"config/config_entries/entry/{ha_id}")

    async def pull(self, state_dir: Path, client: HAClient) -> list[str]:
        # ponytail: no import of existing entries; define them in config_helpers.yaml.
        return []


register(ConfigHelpersProvider())
