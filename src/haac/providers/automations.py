"""Automations provider — CRUD via REST API."""

from pathlib import Path
import yaml

from haac.client import HAClient
from haac.models import Change, ProviderResult, Unmanaged
from haac.providers import Provider, register


class AutomationsProvider(Provider):
    name = "automations"
    state_file = "automations.yaml"
    depends_on = ["entities"]

    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        data = yaml.safe_load(path.read_text()) or {}
        return data.get("automations", [])

    async def read_current(self, client: HAClient) -> list[dict]:
        # REST API returns list of automation configs
        try:
            return await client.rest_get("config/automation/config")
        except Exception:
            return []

    def diff(self, desired: list[dict], current: list[dict], context: dict | None = None) -> ProviderResult:
        result = ProviderResult(provider_name=self.name)
        current_by_id = {a["id"]: a for a in current if "id" in a}
        desired_ids = set()

        for automation in desired:
            aid = automation["id"]
            desired_ids.add(aid)
            ha_auto = current_by_id.get(aid)

            if ha_auto is None:
                result.changes.append(Change(
                    action="create", resource_type="automation",
                    name=automation.get("alias", aid),
                    data=automation,
                ))
            else:
                # Compare key fields
                details = []
                if ha_auto.get("alias", "") != automation.get("alias", ""):
                    details.append(f"alias: {ha_auto.get('alias', '')} → {automation.get('alias', '')}")
                if ha_auto.get("triggers") != automation.get("triggers"):
                    details.append("triggers changed")
                if ha_auto.get("conditions") != automation.get("conditions"):
                    details.append("conditions changed")
                if ha_auto.get("actions") != automation.get("actions"):
                    details.append("actions changed")
                if ha_auto.get("description", "") != automation.get("description", ""):
                    details.append("description changed")

                if details:
                    result.changes.append(Change(
                        action="update", resource_type="automation",
                        name=automation.get("alias", aid),
                        details=details, data=automation, ha_id=aid,
                    ))

        # Unmanaged: automations in HA with IDs not in desired
        for auto in current:
            if auto.get("id") and auto["id"] not in desired_ids:
                result.unmanaged.append(Unmanaged(
                    resource_type="automation",
                    ha_id=auto["id"],
                    name=auto.get("alias", auto["id"]),
                ))

        return result

    async def apply_change(self, client: HAClient, change: Change) -> None:
        aid = change.data["id"]
        # POST the full automation config (minus the id field in the body)
        body = {k: v for k, v in change.data.items() if k != "id"}
        await client.rest_post(f"config/automation/config/{aid}", body)

    async def delete(self, client: HAClient, ha_id: str) -> None:
        await client.rest_delete(f"config/automation/config/{ha_id}")


register(AutomationsProvider())
