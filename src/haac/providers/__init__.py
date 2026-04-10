"""Provider interface and registry."""

from abc import ABC, abstractmethod
from pathlib import Path

import yaml

from haac.client import HAClient
from haac.models import Change, HaacConfigError, ProviderResult


def parse_state_file(path: Path, root_key: str, required_fields: list[str]) -> list[dict]:
    """Parse a YAML state file with structure and field validation.

    Returns the list of entries under root_key.
    Raises HaacConfigError with a clear message on any problem.
    """
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise HaacConfigError(path.name, f"YAML parse error: {e}")

    if not isinstance(data, dict) or root_key not in data:
        raise HaacConfigError(path.name, f"expected a '{root_key}' key containing a list")

    entries = data[root_key]
    if not isinstance(entries, list):
        raise HaacConfigError(path.name, f"expected '{root_key}' to be a list, got {type(entries).__name__}")

    for i, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            raise HaacConfigError(path.name, f"entry #{i} must be a mapping, got {type(entry).__name__}")
        for field in required_fields:
            if field not in entry:
                raise HaacConfigError(path.name, f"entry #{i} is missing required field '{field}'")
            if not entry[field] and entry[field] != 0:
                raise HaacConfigError(path.name, f"entry #{i} has empty required field '{field}'")

    return entries


class Provider(ABC):
    name: str
    state_file: str
    depends_on: list[str] = []

    def has_state_file(self, state_dir: Path) -> bool:
        return (state_dir / self.state_file).exists()

    @abstractmethod
    async def read_desired(self, state_dir: Path) -> list[dict]: ...

    @abstractmethod
    async def read_current(self, client: HAClient) -> list[dict]: ...

    @abstractmethod
    def diff(self, desired: list[dict], current: list[dict], context: dict | None = None) -> ProviderResult: ...

    @abstractmethod
    async def apply_change(self, client: HAClient, change: Change) -> None: ...

    @abstractmethod
    async def delete(self, client: HAClient, ha_id: str) -> None: ...

    async def write_desired(self, state_dir: Path, resources: list[dict]) -> None:
        class _IndentedDumper(yaml.Dumper):
            def increase_indent(self, flow=False, indentless=False):
                return super().increase_indent(flow, False)

        state_dir.mkdir(parents=True, exist_ok=True)
        path = state_dir / self.state_file
        data = {self.name: resources}
        content = yaml.dump(data, Dumper=_IndentedDumper, default_flow_style=False,
                           sort_keys=False, allow_unicode=True)
        path.write_text(f"---\n{content}")

    async def pull(self, state_dir: Path, client: HAClient) -> list[str]:
        """Pull current HA state into state file.

        Returns list of names/IDs of newly added items.
        """
        current = await self.read_current(client)
        if self.has_state_file(state_dir):
            desired = await self.read_desired(state_dir)
        else:
            desired = []

        # Default: additive merge by name
        desired_names = set()
        for d in desired:
            name = d.get("name", d.get("entity_id", d.get("match", "")))
            if name:
                desired_names.add(name.lower())

        new_items = []
        new_names = []
        for item in current:
            name = item.get("name", item.get("name_by_user") or item.get("name", ""))
            if name and name.lower() not in desired_names:
                new_items.append(item)
                new_names.append(name)

        if new_items:
            await self.write_desired(state_dir, desired + new_items)

        return new_names


_PROVIDERS: list[Provider] = []


def register(provider: Provider) -> None:
    _PROVIDERS.append(provider)


def get_providers() -> list[Provider]:
    return list(_PROVIDERS)


def get_provider(name: str) -> Provider | None:
    return next((p for p in _PROVIDERS if p.name == name), None)
