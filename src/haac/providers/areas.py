"""Areas provider — CRUD via WebSocket. Areas depend on floors."""

from pathlib import Path

from haac.client import HAClient
from haac.models import Change, ProviderResult, Unmanaged
from haac.providers import Provider, parse_state_file, register, _try_detect_rename


class AreasProvider(Provider):
    name = "areas"
    state_file = "areas.yaml"
    depends_on = ["floors"]

    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        return parse_state_file(path, "areas", ["name"])

    async def read_current(self, client: HAClient) -> list[dict]:
        return await client.ws_command("config/area_registry/list")

    def _resolve_floor_id(
        self,
        our_floor_id: str | None,
        desired_floors: list[dict],
        ha_floors: list[dict],
    ) -> str | None:
        """Resolve our floor ID (e.g. 'ground') to HA's floor_id.

        Path: our_floor_id → desired_floors name → ha_floors floor_id
        """
        if not our_floor_id:
            return None
        # Find the desired floor entry with our ID → get its name
        desired_floor = next((f for f in desired_floors if f.get("id") == our_floor_id), None)
        if desired_floor is None:
            return None
        floor_name = desired_floor["name"]
        # Find matching HA floor by name (case-insensitive)
        ha_floor = next((f for f in ha_floors if f["name"].lower() == floor_name.lower()), None)
        if ha_floor is None:
            return None
        return ha_floor["floor_id"]

    def diff(self, desired: list[dict], current: list[dict], context: dict | None = None) -> ProviderResult:
        result = ProviderResult(provider_name=self.name)
        context = context or {}
        ha_floors = context.get("floors", [])
        desired_floors = context.get("desired_floors", [])

        current_by_name = {a["name"].lower(): a for a in current}
        matched_ha_ids = set()

        for area in desired:
            ha = current_by_name.get(area["name"].lower())
            resolved_floor_id = self._resolve_floor_id(
                area.get("floor"), desired_floors, ha_floors
            )

            if ha is not None:
                # Match by name — normal update path
                matched_ha_ids.add(ha["area_id"])
                details = []
                if ha.get("icon", "") != area.get("icon", ""):
                    details.append(
                        f"icon: {ha.get('icon', '') or '(none)'} → {area.get('icon', '')}"
                    )
                ha_floor_id = ha.get("floor_id") or None
                if ha_floor_id != resolved_floor_id:
                    details.append(
                        f"floor: {ha_floor_id or '(none)'} → {resolved_floor_id or '(none)'}"
                    )
                if details:
                    result.changes.append(Change(
                        action="update",
                        resource_type="area",
                        name=area["name"],
                        details=details,
                        data={
                            "name": area["name"],
                            "icon": area.get("icon", ""),
                            "floor_id": resolved_floor_id,
                        },
                        ha_id=ha["area_id"],
                    ))
                continue

            # Name not found in HA — check for rename via git
            rename_change = _try_detect_rename(
                desired_entry=area, current_by_name=current_by_name,
                git_ctx=context.get("git_ctx"), state_dir=context.get("state_dir"),
                state_file=self.state_file, root_key="areas",
                resource_type="area", ha_id_field="area_id", name_field="name",
            )
            if rename_change is not None:
                # Merge in icon/floor updates if they changed too
                if rename_change.ha_id:
                    old_ha = next((a for a in current if a["area_id"] == rename_change.ha_id), None)
                    if old_ha:
                        if old_ha.get("icon", "") != area.get("icon", ""):
                            rename_change.details.append(
                                f"icon: {old_ha.get('icon', '') or '(none)'} → {area.get('icon', '')}"
                            )
                        ha_floor_id = old_ha.get("floor_id") or None
                        if ha_floor_id != resolved_floor_id:
                            rename_change.details.append(
                                f"floor: {ha_floor_id or '(none)'} → {resolved_floor_id or '(none)'}"
                            )
                        rename_change.data["icon"] = area.get("icon", "")
                        rename_change.data["floor_id"] = resolved_floor_id
                matched_ha_ids.add(rename_change.ha_id)
                result.changes.append(rename_change)
                continue

            # Truly new area
            result.changes.append(Change(
                action="create",
                resource_type="area",
                name=area["name"],
                data={
                    "name": area["name"],
                    "icon": area.get("icon", ""),
                    "floor_id": resolved_floor_id,
                },
            ))

        for a in current:
            if a["area_id"] not in matched_ha_ids:
                result.unmanaged.append(
                    Unmanaged(resource_type="area", ha_id=a["area_id"], name=a["name"])
                )

        return result

    async def apply_change(self, client: HAClient, change: Change) -> None:
        if change.action == "create":
            await client.ws_command("config/area_registry/create", **change.data)
        elif change.action in ("update", "rename"):
            await client.ws_command(
                "config/area_registry/update", area_id=change.ha_id, **change.data
            )

    async def delete(self, client: HAClient, ha_id: str) -> None:
        await client.ws_command("config/area_registry/delete", area_id=ha_id)


register(AreasProvider())
