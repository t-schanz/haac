"""Helpers provider — input_boolean CRUD via WebSocket API."""

from pathlib import Path

from haac.client import HAClient
from haac.models import Change, ProviderResult, Unmanaged
from haac.providers import Provider, parse_state_file, register, _try_detect_rename


class HelpersProvider(Provider):
    name = "helpers"
    state_file = "helpers.yaml"
    depends_on = []

    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        return parse_state_file(path, "input_booleans", ["name"])

    async def read_current(self, client: HAClient) -> list[dict]:
        try:
            return await client.ws_command("input_boolean/list")
        except RuntimeError:
            return []

    def diff(self, desired: list[dict], current: list[dict], context: dict | None = None) -> ProviderResult:
        result = ProviderResult(provider_name=self.name)
        context = context or {}
        current_by_name = {h["name"].lower(): h for h in current if "name" in h}
        matched_ha_ids = set()

        for helper in desired:
            ha_helper = current_by_name.get(helper.get("name", "").lower())

            if ha_helper is not None:
                # Match by name — normal update path
                matched_ha_ids.add(ha_helper["id"])
                details = []
                if ha_helper.get("icon", "") != helper.get("icon", ""):
                    details.append(f"icon: {ha_helper.get('icon', '') or '(none)'} → {helper.get('icon', '')}")

                if details:
                    result.changes.append(Change(
                        action="update", resource_type="input_boolean",
                        name=helper.get("name", helper["id"]),
                        details=details, data=helper,
                        ha_id=ha_helper["id"],  # HA's actual ID
                    ))
                continue

            # Name not found in HA — check for rename via git
            rename_change = _try_detect_rename(
                desired_entry=helper, current_by_name=current_by_name,
                git_ctx=context.get("git_ctx"), state_dir=context.get("state_dir"),
                state_file=self.state_file, root_key="input_booleans",
                resource_type="input_boolean", ha_id_field="id", name_field="name",
            )
            if rename_change is not None:
                # Add icon update if it differs too
                if rename_change.ha_id:
                    old_ha = next((h for h in current if h["id"] == rename_change.ha_id), None)
                    if old_ha and old_ha.get("icon", "") != helper.get("icon", ""):
                        rename_change.details.append(
                            f"icon: {old_ha.get('icon', '') or '(none)'} → {helper.get('icon', '')}"
                        )
                        rename_change.data["icon"] = helper.get("icon", "")
                matched_ha_ids.add(rename_change.ha_id)
                result.changes.append(rename_change)
                continue

            # Truly new helper
            result.changes.append(Change(
                action="create", resource_type="input_boolean",
                name=helper.get("name", helper["id"]),
                data=helper,
            ))

        for helper in current:
            if helper["id"] not in matched_ha_ids:
                name = helper.get("name", "")
                if name:
                    result.unmanaged.append(Unmanaged(
                        resource_type="input_boolean",
                        ha_id=helper["id"],
                        name=name,
                    ))

        return result

    async def apply_change(self, client: HAClient, change: Change) -> None:
        if change.action == "create":
            await client.ws_command(
                "input_boolean/create",
                name=change.data.get("name", change.data["id"]),
                icon=change.data.get("icon", ""),
            )
        elif change.action in ("update", "rename"):
            await client.ws_command(
                "input_boolean/update",
                input_boolean_id=change.ha_id,
                name=change.data.get("name", ""),
                icon=change.data.get("icon", ""),
            )

    async def delete(self, client: HAClient, ha_id: str) -> None:
        await client.ws_command("input_boolean/delete", input_boolean_id=ha_id)


register(HelpersProvider())
