"""Dashboard provider — Lovelace config via WebSocket."""

from pathlib import Path
import yaml

from haac.client import HAClient
from haac.models import Change, HaacConfigError, ProviderResult
from haac.providers import Provider, register


# Keys in dashboard.yaml that describe the sidebar entry, not the Lovelace config.
META_KEYS = ("url_path", "icon")


def _split(data: dict) -> tuple[dict, dict]:
    meta = {k: data[k] for k in META_KEYS if k in data}
    return meta, {k: v for k, v in data.items() if k not in META_KEYS}


class DashboardProvider(Provider):
    name = "dashboard"
    state_file = "dashboard.yaml"
    depends_on = []
    # With `url_path` set, haac manages a separate storage dashboard (own sidebar entry,
    # titled by `title`). Without it, the default dashboard, which recent HA versions
    # no longer show (/lovelace redirects to the auto-generated home page).
    _url_path: str | None = None

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
        url_path = data.get("url_path")
        if url_path is not None and "-" not in str(url_path):
            raise HaacConfigError(path.name, "url_path must contain a hyphen (HA requirement)")
        self._url_path = url_path
        return [data]

    async def read_current(self, client: HAClient) -> list[dict]:
        if not self._url_path:
            try:
                return [await client.ws_command("lovelace/config")]
            except RuntimeError:
                return []
        dashboards = await client.ws_command("lovelace/dashboards/list")
        entry = next((d for d in dashboards if d.get("url_path") == self._url_path), None)
        if entry is None:
            return []
        try:
            config = await client.ws_command("lovelace/config", url_path=self._url_path)
        except RuntimeError:
            config = {}  # dashboard exists but has never been saved
        meta = {"url_path": self._url_path, **({"icon": entry["icon"]} if entry.get("icon") else {})}
        return [{**config, **meta, "_entry": entry}]

    def diff(self, desired: list[dict], current: list[dict], context: dict | None = None) -> ProviderResult:
        result = ProviderResult(provider_name=self.name)
        if not desired:
            return result

        desired_config = desired[0]
        current_config = dict(current[0]) if current else {}
        entry = current_config.pop("_entry", None)
        title_changed = entry is not None and entry.get("title") != desired_config.get("title")

        if desired_config != current_config or title_changed:
            views = len(desired_config.get("views", []))
            cards = sum(len(v.get("cards", [])) for v in desired_config.get("views", []))
            creating = "url_path" in desired_config and not current
            result.changes.append(Change(
                action="create" if creating else "update", resource_type="dashboard",
                name=desired_config.get("url_path", "Lovelace"),
                details=[f"{views} views, {cards} cards"],
                data=desired_config,
                ha_id=entry["id"] if entry else None,
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
        meta, config = _split(change.data)
        url_path = meta.get("url_path")
        if url_path is None:
            await client.ws_command("lovelace/config/save", config=config)
            return
        sidebar = {"title": config.get("title", url_path), "icon": meta.get("icon"),
                   "show_in_sidebar": True, "require_admin": False}
        sidebar = {k: v for k, v in sidebar.items() if v is not None}
        if change.ha_id is None:
            await client.ws_command("lovelace/dashboards/create", url_path=url_path, mode="storage", **sidebar)
        else:
            await client.ws_command("lovelace/dashboards/update", dashboard_id=change.ha_id, **sidebar)
        await client.ws_command("lovelace/config/save", config=config, url_path=url_path)

    async def delete(self, client: HAClient, ha_id: str) -> None:
        # Dashboard has no delete operation
        pass


register(DashboardProvider())
