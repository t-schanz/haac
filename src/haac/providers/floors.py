"""Floors provider — CRUD via WebSocket."""

from pathlib import Path

from haac.client import HAClient
from haac.models import Change, ProviderResult, Unmanaged
from haac.providers import Provider, parse_state_file, register, _try_detect_rename


class FloorsProvider(Provider):
    name = "floors"
    state_file = "floors.yaml"
    depends_on = []

    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        return parse_state_file(path, "floors", ["name"])

    async def read_current(self, client: HAClient) -> list[dict]:
        return await client.ws_command("config/floor_registry/list")

    def diff(self, desired: list[dict], current: list[dict], context: dict | None = None) -> ProviderResult:
        result = ProviderResult(provider_name=self.name)
        context = context or {}
        current_by_name = {f["name"].lower(): f for f in current}
        matched_ha_ids = set()

        for floor in desired:
            desired_name = floor["name"]
            ha = current_by_name.get(desired_name.lower())

            if ha is not None:
                # Match by name — normal update path
                matched_ha_ids.add(ha["floor_id"])
                details = []
                if ha.get("icon", "") != floor.get("icon", ""):
                    details.append(f"icon: {ha.get('icon', '') or '(none)'} → {floor.get('icon', '')}")
                if details:
                    result.changes.append(Change(
                        action="update", resource_type="floor", name=desired_name,
                        details=details,
                        data={"name": desired_name, "icon": floor.get("icon", "")},
                        ha_id=ha["floor_id"],
                    ))
                continue

            # Name not found in HA — check for rename via git
            rename_change = _try_detect_rename(
                desired_entry=floor, current_by_name=current_by_name,
                git_ctx=context.get("git_ctx"), state_dir=context.get("state_dir"),
                state_file=self.state_file, root_key="floors",
                resource_type="floor", ha_id_field="floor_id", name_field="name",
            )
            if rename_change is not None:
                # Add icon update if it differs too
                if rename_change.ha_id:
                    old_ha = next((c for c in current if c["floor_id"] == rename_change.ha_id), None)
                    if old_ha and old_ha.get("icon", "") != floor.get("icon", ""):
                        rename_change.details.append(
                            f"icon: {old_ha.get('icon', '') or '(none)'} → {floor.get('icon', '')}"
                        )
                        rename_change.data["icon"] = floor.get("icon", "")
                matched_ha_ids.add(rename_change.ha_id)
                result.changes.append(rename_change)
                continue

            # Truly new floor
            result.changes.append(Change(
                action="create", resource_type="floor", name=desired_name,
                data={"name": desired_name, "icon": floor.get("icon", "")},
            ))

        for f in current:
            if f["floor_id"] not in matched_ha_ids:
                result.unmanaged.append(Unmanaged(
                    resource_type="floor", ha_id=f["floor_id"], name=f["name"],
                ))

        return result

    async def apply_change(self, client: HAClient, change: Change) -> None:
        if change.action == "create":
            await client.ws_command("config/floor_registry/create", **change.data)
        elif change.action in ("update", "rename"):
            await client.ws_command("config/floor_registry/update", floor_id=change.ha_id, **change.data)

    async def delete(self, client: HAClient, ha_id: str) -> None:
        await client.ws_command("config/floor_registry/delete", floor_id=ha_id)


register(FloorsProvider())
