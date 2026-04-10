"""Scenes provider — CRUD via REST API."""

from pathlib import Path
import yaml

from haac.client import HAClient
from haac.models import Change, ProviderResult, Unmanaged
from haac.providers import Provider, register


class ScenesProvider(Provider):
    name = "scenes"
    state_file = "scenes.yaml"
    depends_on = []

    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        data = yaml.safe_load(path.read_text()) or {}
        return data.get("scenes", [])

    async def read_current(self, client: HAClient) -> list[dict]:
        try:
            return await client.rest_get("config/scene/config")
        except Exception:
            return []

    def diff(self, desired: list[dict], current: list[dict], context: dict | None = None) -> ProviderResult:
        result = ProviderResult(provider_name=self.name)
        current_by_id = {s["id"]: s for s in current if "id" in s}
        desired_ids = set()

        for scene in desired:
            sid = scene["id"]
            desired_ids.add(sid)
            ha_scene = current_by_id.get(sid)

            if ha_scene is None:
                result.changes.append(Change(
                    action="create", resource_type="scene",
                    name=scene.get("name", sid),
                    data=scene,
                ))
            else:
                details = []
                if ha_scene.get("name", "") != scene.get("name", ""):
                    details.append(f"name: {ha_scene.get('name', '')} → {scene.get('name', '')}")
                if ha_scene.get("entities") != scene.get("entities"):
                    details.append("entities changed")

                if details:
                    result.changes.append(Change(
                        action="update", resource_type="scene",
                        name=scene.get("name", sid),
                        details=details, data=scene, ha_id=sid,
                    ))

        for scene in current:
            if scene.get("id") and scene["id"] not in desired_ids:
                result.unmanaged.append(Unmanaged(
                    resource_type="scene",
                    ha_id=scene["id"],
                    name=scene.get("name", scene["id"]),
                ))

        return result

    async def apply_change(self, client: HAClient, change: Change) -> None:
        sid = change.data["id"]
        body = {k: v for k, v in change.data.items() if k != "id"}
        await client.rest_post(f"config/scene/config/{sid}", body)

    async def delete(self, client: HAClient, ha_id: str) -> None:
        await client.rest_delete(f"config/scene/config/{ha_id}")


register(ScenesProvider())
