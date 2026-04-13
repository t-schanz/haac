"""Labels provider — CRUD via WebSocket."""

from pathlib import Path

from haac.client import HAClient
from haac.models import Change, ProviderResult, Unmanaged
from haac.providers import Provider, parse_state_file, register, _try_detect_rename


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
        context = context or {}
        current_by_name = {lb["name"].lower(): lb for lb in current}
        matched_ha_ids = set()

        for label in desired:
            ha = current_by_name.get(label["name"].lower())

            if ha is not None:
                # Match by name — normal update path
                matched_ha_ids.add(ha["label_id"])
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
                continue

            # Name not found in HA — check for rename via git
            rename_change = _try_detect_rename(
                desired_entry=label, current_by_name=current_by_name,
                git_ctx=context.get("git_ctx"), state_dir=context.get("state_dir"),
                state_file=self.state_file, root_key="labels",
                resource_type="label", ha_id_field="label_id", name_field="name",
            )
            if rename_change is not None:
                # Add icon/color updates if they differ too
                if rename_change.ha_id:
                    old_ha = next((c for c in current if c["label_id"] == rename_change.ha_id), None)
                    if old_ha:
                        if old_ha.get("icon", "") != label.get("icon", ""):
                            rename_change.details.append(
                                f"icon: {old_ha.get('icon', '') or '(none)'} → {label.get('icon', '')}"
                            )
                            rename_change.data["icon"] = label.get("icon", "")
                        if old_ha.get("color", "") != label.get("color", ""):
                            rename_change.details.append(
                                f"color: {old_ha.get('color', '') or '(none)'} → {label.get('color', '')}"
                            )
                            rename_change.data["color"] = label.get("color", "")
                matched_ha_ids.add(rename_change.ha_id)
                result.changes.append(rename_change)
                continue

            # Truly new label
            result.changes.append(Change(
                action="create", resource_type="label", name=label["name"],
                data={
                    "name": label["name"],
                    "icon": label.get("icon", ""),
                    "color": label.get("color", ""),
                },
            ))

        for lb in current:
            if lb["label_id"] not in matched_ha_ids:
                result.unmanaged.append(Unmanaged(resource_type="label", ha_id=lb["label_id"], name=lb["name"]))

        return result

    async def apply_change(self, client: HAClient, change: Change) -> None:
        if change.action == "create":
            await client.ws_command("config/label_registry/create", **change.data)
        elif change.action in ("update", "rename"):
            await client.ws_command("config/label_registry/update", label_id=change.ha_id, **change.data)

    async def delete(self, client: HAClient, ha_id: str) -> None:
        await client.ws_command("config/label_registry/delete", label_id=ha_id)


register(LabelsProvider())
