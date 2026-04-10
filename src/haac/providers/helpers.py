"""Helpers provider — input_boolean CRUD via REST API."""

from pathlib import Path
import yaml

from haac.client import HAClient
from haac.models import Change, ProviderResult, Unmanaged
from haac.providers import Provider, register


class HelpersProvider(Provider):
    name = "helpers"
    state_file = "helpers.yaml"
    depends_on = []

    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        data = yaml.safe_load(path.read_text()) or {}
        return data.get("input_booleans", [])

    async def read_current(self, client: HAClient) -> list[dict]:
        # REST API returns a dict: {id: {name, icon, ...}, ...}
        try:
            raw = await client.rest_get("config/input_boolean/config")
            return [{"id": k, **v} for k, v in raw.items()]
        except Exception:
            return []

    def diff(self, desired: list[dict], current: list[dict], context: dict | None = None) -> ProviderResult:
        result = ProviderResult(provider_name=self.name)
        current_by_id = {h["id"]: h for h in current if "id" in h}
        desired_ids = set()

        for helper in desired:
            hid = helper["id"]
            desired_ids.add(hid)
            ha_helper = current_by_id.get(hid)

            if ha_helper is None:
                result.changes.append(Change(
                    action="create", resource_type="input_boolean",
                    name=helper.get("name", hid),
                    data=helper,
                ))
            else:
                details = []
                if ha_helper.get("name", "") != helper.get("name", ""):
                    details.append(f"name: {ha_helper.get('name', '')} → {helper.get('name', '')}")
                if ha_helper.get("icon", "") != helper.get("icon", ""):
                    details.append(f"icon: {ha_helper.get('icon', '') or '(none)'} → {helper.get('icon', '')}")

                if details:
                    result.changes.append(Change(
                        action="update", resource_type="input_boolean",
                        name=helper.get("name", hid),
                        details=details, data=helper, ha_id=hid,
                    ))

        for helper in current:
            if helper.get("id") and helper["id"] not in desired_ids:
                result.unmanaged.append(Unmanaged(
                    resource_type="input_boolean",
                    ha_id=helper["id"],
                    name=helper.get("name", helper["id"]),
                ))

        return result

    async def apply_change(self, client: HAClient, change: Change) -> None:
        hid = change.data["id"]
        body = {k: v for k, v in change.data.items() if k != "id"}
        await client.rest_post(f"config/input_boolean/config/{hid}", body)

    async def delete(self, client: HAClient, ha_id: str) -> None:
        await client.rest_delete(f"config/input_boolean/config/{ha_id}")


register(HelpersProvider())
