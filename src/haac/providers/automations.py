"""Automations provider — CRUD via REST API."""

from pathlib import Path

from haac.client import HAClient
from haac.models import Change, ProviderResult, Unmanaged
from haac.providers import Provider, parse_state_file, register, git_head_entry


class AutomationsProvider(Provider):
    name = "automations"
    state_file = "automations.yaml"
    depends_on = ["entities"]

    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        return parse_state_file(path, "automations", ["id"])

    async def read_current(self, client: HAClient) -> list[dict]:
        # Get automation entity states (which contain the 'id' attribute)
        try:
            states = await client.rest_get("states")
        except Exception:
            return []
        auto_states = [s for s in states if s["entity_id"].startswith("automation.")]

        result = []
        for state in auto_states:
            auto_id = state["attributes"].get("id", "")
            if not auto_id:
                continue
            try:
                config = await client.rest_get(f"config/automation/config/{auto_id}")
                result.append(config)
            except Exception:
                continue
        return result

    def diff(self, desired: list[dict], current: list[dict], context: dict | None = None) -> ProviderResult:
        result = ProviderResult(provider_name=self.name)
        current_by_id = {a["id"]: a for a in current if "id" in a}
        desired_ids = set()

        for automation in desired:
            aid = automation["id"]
            desired_ids.add(aid)
            ha_auto = current_by_id.get(aid)

            if ha_auto is None:
                # Check for rename: same haac_id, different id in HEAD
                haac_id = automation.get("haac_id")
                git_ctx = (context or {}).get("git_ctx")
                state_dir = (context or {}).get("state_dir")
                if haac_id and git_ctx is not None and state_dir is not None:
                    abs_path = Path(state_dir) / self.state_file
                    try:
                        rel_path = abs_path.relative_to(git_ctx.root)
                    except ValueError:
                        rel_path = abs_path
                    old_entry = git_head_entry(git_ctx, rel_path, "automations", haac_id)
                    if old_entry is not None:
                        old_id = old_entry.get("id")
                        if old_id and any(a.get("id") == old_id for a in current):
                            result.changes.append(Change(
                                action="rename",
                                resource_type="automation",
                                name=f"{old_id} → {aid}",
                                details=[f"id: {old_id} → {aid}"],
                                data={"new_id": aid, "config": automation},
                                ha_id=old_id,
                            ))
                            continue  # Don't also emit a create
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
        if change.action == "rename":
            new_id = change.data["new_id"]
            config = change.data["config"]
            clean_config = {k: v for k, v in config.items() if k not in ("id", "haac_id")}
            await client.rest_post(f"config/automation/config/{new_id}", clean_config)
            try:
                await client.rest_delete(f"config/automation/config/{change.ha_id}")
            except Exception as e:
                from haac.output import console
                console.print(
                    f"[yellow]Warning: renamed automation created new id "
                    f"{new_id} but failed to delete old id {change.ha_id}: {e}[/yellow]"
                )
        else:
            aid = change.data["id"]
            # POST the full automation config (minus the id field in the body)
            body = {k: v for k, v in change.data.items() if k not in ("id", "haac_id")}
            await client.rest_post(f"config/automation/config/{aid}", body)

    async def delete(self, client: HAClient, ha_id: str) -> None:
        await client.rest_delete(f"config/automation/config/{ha_id}")


register(AutomationsProvider())
