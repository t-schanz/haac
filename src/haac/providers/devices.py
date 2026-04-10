"""Devices provider — assigns devices to areas via glob pattern matching."""

from fnmatch import fnmatch
from pathlib import Path
import yaml

from haac.client import HAClient
from haac.models import Change, ProviderResult, Unmanaged
from haac.providers import Provider, register


class DevicesProvider(Provider):
    name = "devices"
    state_file = "assignments.yaml"
    depends_on = ["areas"]

    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        data = yaml.safe_load(path.read_text()) or {}
        return data.get("devices", [])

    async def read_current(self, client: HAClient) -> list[dict]:
        return await client.ws_command("config/device_registry/list")

    def _resolve_area_id(
        self,
        our_area_id: str,
        desired_areas: list[dict],
        ha_areas: list[dict],
    ) -> str | None:
        """Resolve our area ID (e.g. 'living_room') to HA's area_id.

        Path: our_area_id → desired_areas name → ha_areas area_id
        """
        desired_area = next((a for a in desired_areas if a.get("id") == our_area_id), None)
        if desired_area is None:
            return None
        area_name = desired_area["name"]
        ha_area = next((a for a in ha_areas if a["name"].lower() == area_name.lower()), None)
        if ha_area is None:
            return None
        return ha_area["area_id"]

    def diff(self, desired: list[dict], current: list[dict], context: dict | None = None) -> ProviderResult:
        result = ProviderResult(provider_name=self.name)
        context = context or {}
        ha_areas = context.get("areas", [])
        desired_areas = context.get("desired_areas", [])

        for device in current:
            device_name = device.get("name_by_user") or device.get("name") or ""
            current_area_id = device.get("area_id")

            # Last-match-wins: iterate all rules and keep final match
            matched_area_our_id = None
            for rule in desired:
                if fnmatch(device_name, rule["match"]):
                    matched_area_our_id = rule["area"]

            if matched_area_our_id is None:
                # No rule matched — report as unmanaged if it has an area
                if current_area_id:
                    # Reverse-lookup area name for display
                    area_name = next(
                        (a["name"] for a in ha_areas if a["area_id"] == current_area_id),
                        current_area_id,
                    )
                    result.unmanaged.append(Unmanaged(
                        resource_type="device",
                        ha_id=device["id"],
                        name=f"{device_name} → {area_name}",
                    ))
                continue

            target_area_id = self._resolve_area_id(matched_area_our_id, desired_areas, ha_areas)

            if current_area_id != target_area_id:
                result.changes.append(Change(
                    action="update",
                    resource_type="device",
                    name=device_name,
                    details=[f"area: {current_area_id or '(none)'} → {target_area_id or '(none)'}"],
                    data={"area_id": target_area_id},
                    ha_id=device["id"],
                ))

        return result

    async def apply_change(self, client: HAClient, change: Change) -> None:
        if change.action == "update":
            await client.ws_command(
                "config/device_registry/update",
                device_id=change.ha_id,
                area_id=change.data["area_id"],
            )

    async def delete(self, client: HAClient, ha_id: str) -> None:
        raise NotImplementedError("Devices cannot be deleted via haac")

    async def write_desired(self, state_dir: Path, resources: list[dict]) -> None:
        """No-op — device assignments use glob patterns, not raw entries."""
        pass


register(DevicesProvider())
