"""Dashboard provider — Lovelace config via WebSocket."""

from pathlib import Path
import yaml

from haac.client import HAClient
from haac.models import Change, HaacConfigError, ProviderResult
from haac.providers import Provider, register


class DashboardProvider(Provider):
    name = "dashboard"
    state_file = "dashboard.yaml"
    depends_on = []

    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        try:
            data = yaml.safe_load(path.read_text())
        except yaml.YAMLError as e:
            raise HaacConfigError(path.name, f"YAML parse error: {e}")
        if not isinstance(data, dict):
            raise HaacConfigError(path.name, "expected a YAML mapping at the top level")
        if "views" in data and not isinstance(data["views"], list):
            raise HaacConfigError(path.name, "expected 'views' to be a list")
        return [data]

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

    async def pull(self, state_dir: Path, client: HAClient) -> list[str]:
        # The dashboard is one document, not a list of entries: never merge into an
        # existing file, and write it flat (title/views) so read_desired can parse it.
        path = state_dir / self.state_file
        if path.exists():
            return []
        current = await self.read_current(client)
        if not current:
            return []
        state_dir.mkdir(parents=True, exist_ok=True)
        content = yaml.dump(current[0], default_flow_style=False, sort_keys=False, allow_unicode=True)
        path.write_text(f"---\n{content}")
        return ["Lovelace"]

    async def apply_change(self, client: HAClient, change: Change) -> None:
        await client.ws_command("lovelace/config/save", config=change.data)

    async def delete(self, client: HAClient, ha_id: str) -> None:
        # Dashboard has no delete operation
        pass


register(DashboardProvider())
