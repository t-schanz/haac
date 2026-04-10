"""Floors provider — CRUD via WebSocket."""

from pathlib import Path
import yaml

from haac.client import HAClient
from haac.models import Change, ProviderResult, Unmanaged
from haac.providers import Provider, register


class FloorsProvider(Provider):
    name = "floors"
    state_file = "floors.yaml"
    depends_on = []

    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        data = yaml.safe_load(path.read_text()) or {}
        return data.get("floors", [])

    async def read_current(self, client: HAClient) -> list[dict]:
        return await client.ws_command("config/floor_registry/list")

    def diff(self, desired: list[dict], current: list[dict], context: dict | None = None) -> ProviderResult:
        result = ProviderResult(provider_name=self.name)
        current_by_name = {f["name"].lower(): f for f in current}
        matched = set()

        for floor in desired:
            ha = current_by_name.get(floor["name"].lower())
            if ha is None:
                result.changes.append(Change(
                    action="create", resource_type="floor", name=floor["name"],
                    data={"name": floor["name"], "icon": floor.get("icon", "")},
                ))
            else:
                matched.add(floor["name"].lower())
                details = []
                if ha.get("icon", "") != floor.get("icon", ""):
                    details.append(f"icon: {ha.get('icon', '') or '(none)'} → {floor.get('icon', '')}")
                if details:
                    result.changes.append(Change(
                        action="update", resource_type="floor", name=floor["name"],
                        details=details,
                        data={"name": floor["name"], "icon": floor.get("icon", "")},
                        ha_id=ha["floor_id"],
                    ))

        for f in current:
            if f["name"].lower() not in matched and not any(
                d["name"].lower() == f["name"].lower() for d in desired
            ):
                result.unmanaged.append(Unmanaged(resource_type="floor", ha_id=f["floor_id"], name=f["name"]))

        return result

    async def apply_change(self, client: HAClient, change: Change) -> None:
        if change.action == "create":
            await client.ws_command("config/floor_registry/create", **change.data)
        elif change.action == "update":
            await client.ws_command("config/floor_registry/update", floor_id=change.ha_id, **change.data)

    async def delete(self, client: HAClient, ha_id: str) -> None:
        await client.ws_command("config/floor_registry/delete", floor_id=ha_id)


register(FloorsProvider())
