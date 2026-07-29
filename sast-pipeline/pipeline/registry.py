"""Single composition root for library and CLI execution providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ExecutionHandler(Protocol):
    def __call__(self, execution: object) -> object: ...


class ExecutionCommand(Protocol):
    def __call__(self, arguments: list[str], *, analyzer_config) -> object: ...


@dataclass(frozen=True, slots=True)
class ExecutionProvider:
    execution_type: str
    metric_label: str
    operations: frozenset[str]
    execute: ExecutionHandler
    command: ExecutionCommand | None = None

    def __post_init__(self) -> None:
        if self.execution_type != self.execution_type.lower() or not self.execution_type:
            detail = "Execution provider type must be a non-blank lowercase value"
            raise ValueError(detail)
        if not self.metric_label or not self.operations or "execute" not in self.operations:
            detail = "Execution provider must declare a bounded metric label and execute operation"
            raise ValueError(detail)


class ExecutionProviderRegistry:
    def __init__(self, *providers: ExecutionProvider):
        self._providers: dict[str, ExecutionProvider] = {}
        for provider in providers:
            self.register(provider)

    def register(self, provider: ExecutionProvider) -> None:
        if provider.execution_type in self._providers:
            detail = f"Duplicate execution provider: {provider.execution_type}"
            raise ValueError(detail)
        self._providers[provider.execution_type] = provider

    def resolve(self, execution_type: str) -> ExecutionProvider:
        normalized = execution_type.lower()
        try:
            return self._providers[normalized]
        except KeyError:
            detail = f"No execution provider is registered for {normalized}"
            raise ValueError(detail) from None

    def validate_catalog(self, analyzer_config) -> None:
        catalog_types = set(analyzer_config.get_standalone_execution_types())
        executable_types = {
            execution_type
            for execution_type, provider in self._providers.items()
            if provider.command is not None
        }
        if catalog_types != executable_types:
            detail = "Standalone execution catalog and provider registry must match exactly"
            raise ValueError(detail)
