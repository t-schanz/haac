"""Shared models for diff results."""

from dataclasses import dataclass, field


class HaacConfigError(Exception):
    """Raised when a state file has invalid structure or content."""
    def __init__(self, file: str, message: str):
        self.file = file
        super().__init__(f"{file}: {message}")


@dataclass
class ValidationWarning:
    file: str
    message: str


@dataclass
class Change:
    action: str  # "create" | "update"
    resource_type: str
    name: str
    details: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)
    ha_id: str | None = None


@dataclass
class Unmanaged:
    resource_type: str
    ha_id: str
    name: str


@dataclass
class ProviderResult:
    provider_name: str
    changes: list[Change] = field(default_factory=list)
    unmanaged: list[Unmanaged] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.changes)


@dataclass
class PlanResult:
    results: list[ProviderResult] = field(default_factory=list)
    warnings: list[ValidationWarning] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return any(r.has_changes for r in self.results)

    @property
    def total_creates(self) -> int:
        return sum(1 for r in self.results for c in r.changes if c.action == "create")

    @property
    def total_updates(self) -> int:
        return sum(1 for r in self.results for c in r.changes if c.action == "update")

    @property
    def total_unmanaged(self) -> int:
        return sum(len(r.unmanaged) for r in self.results)
