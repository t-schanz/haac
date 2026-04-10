"""Entities provider — customize entity names and icons via WebSocket."""

from pathlib import Path
import yaml

from haac.client import HAClient
from haac.models import Change, ProviderResult, Unmanaged
from haac.providers import Provider, register


class EntitiesProvider(Provider):
    name = "entities"
    state_file = "entities.yaml"
    depends_on = ["areas"]

    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        data = yaml.safe_load(path.read_text()) or {}
        return data.get("entities", [])

    async def read_current(self, client: HAClient) -> list[dict]:
        return await client.ws_command("config/entity_registry/list")

    def diff(self, desired: list[dict], current: list[dict], context: dict | None = None) -> ProviderResult:
        result = ProviderResult(provider_name=self.name)
        # Index current entities by entity_id
        current_by_id = {e["entity_id"]: e for e in current}

        for entity in desired:
            eid = entity["entity_id"]
            ha_entity = current_by_id.get(eid)
            if ha_entity is None:
                # Entity doesn't exist in HA — skip (can't create entities)
                continue

            details = []
            # Compare friendly_name (HA stores user-set name as "name")
            desired_name = entity.get("friendly_name", "")
            current_name = ha_entity.get("name") or ""
            if desired_name and desired_name != current_name:
                details.append(f"name: {current_name or '(default)'} → {desired_name}")

            # Compare icon
            desired_icon = entity.get("icon", "")
            current_icon = ha_entity.get("icon") or ""
            if desired_icon and desired_icon != current_icon:
                details.append(f"icon: {current_icon or '(default)'} → {desired_icon}")

            if details:
                data = {"entity_id": eid}
                if desired_name:
                    data["name"] = desired_name
                if desired_icon:
                    data["icon"] = desired_icon
                result.changes.append(Change(
                    action="update", resource_type="entity",
                    name=eid, details=details, data=data,
                    ha_id=eid,
                ))

        return result

    async def apply_change(self, client: HAClient, change: Change) -> None:
        data = {k: v for k, v in change.data.items() if k != "entity_id"}
        await client.ws_command(
            "config/entity_registry/update",
            entity_id=change.data["entity_id"],
            **data,
        )

    async def delete(self, client: HAClient, ha_id: str) -> None:
        raise NotImplementedError("Entities cannot be deleted via haac")


register(EntitiesProvider())
