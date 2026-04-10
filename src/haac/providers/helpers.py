"""Helpers provider — input_boolean CRUD via WebSocket API."""

from pathlib import Path

from haac.client import HAClient
from haac.models import Change, ProviderResult, Unmanaged
from haac.providers import Provider, parse_state_file, register


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
        current_by_name = {h["name"].lower(): h for h in current if "name" in h}
        matched_names = set()

        for helper in desired:
            ha_helper = current_by_name.get(helper.get("name", "").lower())

            if ha_helper is None:
                result.changes.append(Change(
                    action="create", resource_type="input_boolean",
                    name=helper.get("name", helper["id"]),
                    data=helper,
                ))
            else:
                matched_names.add(helper.get("name", "").lower())
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

        for helper in current:
            name = helper.get("name", "").lower()
            if name and name not in matched_names and not any(
                d.get("name", "").lower() == name for d in desired
            ):
                result.unmanaged.append(Unmanaged(
                    resource_type="input_boolean",
                    ha_id=helper["id"],
                    name=helper.get("name", helper["id"]),
                ))

        return result

    async def apply_change(self, client: HAClient, change: Change) -> None:
        if change.action == "create":
            await client.ws_command(
                "input_boolean/create",
                name=change.data.get("name", change.data["id"]),
                icon=change.data.get("icon", ""),
            )
        elif change.action == "update":
            await client.ws_command(
                "input_boolean/update",
                input_boolean_id=change.ha_id,
                name=change.data.get("name", ""),
                icon=change.data.get("icon", ""),
            )

    async def delete(self, client: HAClient, ha_id: str) -> None:
        await client.ws_command("input_boolean/delete", input_boolean_id=ha_id)


register(HelpersProvider())
