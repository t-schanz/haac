"""Scenes provider — CRUD via REST API."""

from pathlib import Path

from haac.client import HAClient
from haac.models import Change, ProviderResult, Unmanaged
from haac.providers import Provider, parse_state_file, register, git_head_entry


class ScenesProvider(Provider):
    name = "scenes"
    state_file = "scenes.yaml"
    depends_on = []

    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        return parse_state_file(path, "scenes", ["id"])

    async def read_current(self, client: HAClient) -> list[dict]:
        # Get scene entity states (which contain the 'id' attribute)
        try:
            states = await client.rest_get("states")
        except Exception:
            return []
        scene_states = [s for s in states if s["entity_id"].startswith("scene.")]

        result = []
        for state in scene_states:
            scene_id = state["attributes"].get("id", "")
            if not scene_id:
                continue  # Skip Hue-created scenes (no id)
            try:
                config = await client.rest_get(f"config/scene/config/{scene_id}")
                result.append(config)
            except Exception:
                continue
        return result

    def diff(self, desired: list[dict], current: list[dict], context: dict | None = None) -> ProviderResult:
        result = ProviderResult(provider_name=self.name)
        current_by_id = {s["id"]: s for s in current if "id" in s}
        desired_ids = set()

        for scene in desired:
            sid = scene["id"]
            desired_ids.add(sid)
            ha_scene = current_by_id.get(sid)

            if ha_scene is None:
                # Check for rename: same haac_id, different id in HEAD
                haac_id = scene.get("haac_id")
                git_ctx = (context or {}).get("git_ctx")
                state_dir = (context or {}).get("state_dir")
                if haac_id and git_ctx is not None and state_dir is not None:
                    abs_path = Path(state_dir) / self.state_file
                    try:
                        rel_path = abs_path.relative_to(git_ctx.root)
                    except ValueError:
                        rel_path = abs_path
                    old_entry = git_head_entry(git_ctx, rel_path, "scenes", haac_id)
                    if old_entry is not None:
                        old_id = old_entry.get("id")
                        if old_id and any(s.get("id") == old_id for s in current):
                            result.changes.append(Change(
                                action="rename",
                                resource_type="scene",
                                name=f"{old_id} → {sid}",
                                details=[f"id: {old_id} → {sid}"],
                                data={"new_id": sid, "config": scene},
                                ha_id=old_id,
                            ))
                            continue  # Don't also emit a create
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
        if change.action == "rename":
            new_id = change.data["new_id"]
            config = change.data["config"]
            clean_config = {k: v for k, v in config.items() if k not in ("id", "haac_id")}
            await client.rest_post(f"config/scene/config/{new_id}", clean_config)
            try:
                await client.rest_delete(f"config/scene/config/{change.ha_id}")
            except Exception as e:
                from haac.output import console
                console.print(
                    f"[yellow]Warning: renamed scene created new id "
                    f"{new_id} but failed to delete old id {change.ha_id}: {e}[/yellow]"
                )
        else:
            sid = change.data["id"]
            body = {k: v for k, v in change.data.items() if k not in ("id", "haac_id")}
            await client.rest_post(f"config/scene/config/{sid}", body)

    async def delete(self, client: HAClient, ha_id: str) -> None:
        await client.rest_delete(f"config/scene/config/{ha_id}")


register(ScenesProvider())
