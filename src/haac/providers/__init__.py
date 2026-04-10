"""Provider interface and registry."""

from abc import ABC, abstractmethod
from pathlib import Path

import yaml

from haac.client import HAClient
from haac.models import Change, ProviderResult


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


_PROVIDERS: list[Provider] = []


def register(provider: Provider) -> None:
    _PROVIDERS.append(provider)


def get_providers() -> list[Provider]:
    return list(_PROVIDERS)


def get_provider(name: str) -> Provider | None:
    return next((p for p in _PROVIDERS if p.name == name), None)
