"""Entities provider — customize entity names and icons via WebSocket."""

from pathlib import Path
import yaml

from haac.client import HAClient
from haac.models import Change, ProviderResult, Unmanaged
from haac.providers import Provider, parse_state_file, register


class EntitiesProvider(Provider):
    name = "entities"
    state_file = "entities.yaml"
    depends_on = ["areas"]

    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        return parse_state_file(path, "entities", ["entity_id"])

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

    async def write_desired(self, state_dir: Path, resources: list[dict]) -> None:
        """Write entities in haac format (entity_id, friendly_name, icon)."""
        class _IndentedDumper(yaml.Dumper):
            def increase_indent(self, flow=False, indentless=False):
                return super().increase_indent(flow, False)

        converted = []
        for e in resources:
            # Only include entities with customization
            name = e.get("friendly_name") or e.get("name") or ""
            icon = e.get("icon") or ""
            if not name and not icon:
                continue
            entry: dict = {"entity_id": e.get("entity_id", e.get("id", ""))}
            if name:
                entry["friendly_name"] = name
            if icon:
                entry["icon"] = icon
            converted.append(entry)

        if not converted:
            return

        state_dir.mkdir(parents=True, exist_ok=True)
        path = state_dir / self.state_file
        data = {"entities": converted}
        content = yaml.dump(data, Dumper=_IndentedDumper, default_flow_style=False,
                           sort_keys=False, allow_unicode=True)
        path.write_text(f"---\n{content}")

    async def pull(self, state_dir: Path, client: HAClient) -> list[str]:
        """Pull entity customizations from HA."""
        current = await self.read_current(client)
        if self.has_state_file(state_dir):
            desired = await self.read_desired(state_dir)
        else:
            desired = []

        desired_ids = {e["entity_id"] for e in desired}

        new_items = []
        new_names = []
        for entity in current:
            eid = entity.get("entity_id", "")
            name = entity.get("name") or ""
            icon = entity.get("icon") or ""
            if eid not in desired_ids and (name or icon):
                entry: dict = {"entity_id": eid}
                if name:
                    entry["friendly_name"] = name
                if icon:
                    entry["icon"] = icon
                new_items.append(entry)
                new_names.append(eid)

        if new_items:
            await self.write_desired(state_dir, desired + new_items)

        return new_names


register(EntitiesProvider())
