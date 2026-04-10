"""Labels provider — CRUD via WebSocket."""

from pathlib import Path

from haac.client import HAClient
from haac.models import Change, ProviderResult, Unmanaged
from haac.providers import Provider, parse_state_file, register


class LabelsProvider(Provider):
    name = "labels"
    state_file = "labels.yaml"
    depends_on = []

    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        return parse_state_file(path, "labels", ["name"])

    async def read_current(self, client: HAClient) -> list[dict]:
        return await client.ws_command("config/label_registry/list")

    def diff(self, desired: list[dict], current: list[dict], context: dict | None = None) -> ProviderResult:
        result = ProviderResult(provider_name=self.name)
        current_by_name = {lb["name"].lower(): lb for lb in current}
        matched = set()

        for label in desired:
            ha = current_by_name.get(label["name"].lower())
            if ha is None:
                result.changes.append(Change(
                    action="create", resource_type="label", name=label["name"],
                    data={
                        "name": label["name"],
                        "icon": label.get("icon", ""),
                        "color": label.get("color", ""),
                    },
                ))
            else:
                matched.add(label["name"].lower())
                details = []
                if ha.get("icon", "") != label.get("icon", ""):
                    details.append(f"icon: {ha.get('icon', '') or '(none)'} → {label.get('icon', '')}")
                if ha.get("color", "") != label.get("color", ""):
                    details.append(f"color: {ha.get('color', '') or '(none)'} → {label.get('color', '')}")
                if details:
                    result.changes.append(Change(
                        action="update", resource_type="label", name=label["name"],
                        details=details,
                        data={
                            "name": label["name"],
                            "icon": label.get("icon", ""),
                            "color": label.get("color", ""),
                        },
                        ha_id=ha["label_id"],
                    ))

        for lb in current:
            if lb["name"].lower() not in matched and not any(
                d["name"].lower() == lb["name"].lower() for d in desired
            ):
                result.unmanaged.append(Unmanaged(resource_type="label", ha_id=lb["label_id"], name=lb["name"]))

        return result

    async def apply_change(self, client: HAClient, change: Change) -> None:
        if change.action == "create":
            await client.ws_command("config/label_registry/create", **change.data)
        elif change.action == "update":
            await client.ws_command("config/label_registry/update", label_id=change.ha_id, **change.data)

    async def delete(self, client: HAClient, ha_id: str) -> None:
        await client.ws_command("config/label_registry/delete", label_id=ha_id)


register(LabelsProvider())
