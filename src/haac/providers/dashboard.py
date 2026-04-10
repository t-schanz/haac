"""Dashboard provider — Lovelace config via WebSocket."""

from pathlib import Path
import yaml

from haac.client import HAClient
from haac.models import Change, ProviderResult
from haac.providers import Provider, register


class DashboardProvider(Provider):
    name = "dashboard"
    state_file = "dashboard.yaml"
    depends_on = []

    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        data = yaml.safe_load(path.read_text()) or {}
        return [data]  # wrap in list for consistency

    async def read_current(self, client: HAClient) -> list[dict]:
        try:
            config = await client.ws_command("lovelace/config")
            return [config]
        except RuntimeError:
            return []

    def diff(self, desired: list[dict], current: list[dict], context: dict | None = None) -> ProviderResult:
        result = ProviderResult(provider_name=self.name)
        if not desired:
            return result

        desired_config = desired[0]
        current_config = current[0] if current else {}

        if desired_config != current_config:
            views = len(desired_config.get("views", []))
            cards = sum(len(v.get("cards", [])) for v in desired_config.get("views", []))
            result.changes.append(Change(
                action="update", resource_type="dashboard",
                name="Lovelace",
                details=[f"{views} views, {cards} cards"],
                data=desired_config,
            ))

        return result

    async def apply_change(self, client: HAClient, change: Change) -> None:
        await client.ws_command("lovelace/config/save", config=change.data)

    async def delete(self, client: HAClient, ha_id: str) -> None:
        # Dashboard has no delete operation
        pass


register(DashboardProvider())
