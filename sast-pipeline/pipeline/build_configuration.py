"""Typed inputs for preparing a source checkout and running its analyzers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from .bridge_client import BridgeClient
    from .config_utils import AnalyzersConfigHelper


class SourceType(str, Enum):
    GIT_BRANCH = "GIT_BRANCH"
    GIT_HASH = "GIT_HASH"
    FILE_HASH = "FILE_HASH"


@dataclass(frozen=True, slots=True)
class SourceRevision:
    version: str = ""
    type: SourceType | None = None
    extracted_root: str = ""

    @classmethod
    def from_dict(cls, value: dict) -> SourceRevision:
        return cls(
            version=value.get("version", ""),
            type=SourceType(value["type"]) if value.get("type") else None,
            extracted_root=value.get("extracted_root", ""),
        )

    def as_dict(self) -> dict:
        return {"version": self.version, "type": self.type, "extracted_root": self.extracted_root}


@dataclass(frozen=True, slots=True, kw_only=True)
class SastRuntimeConfiguration:
    script_path: str
    output_dir: str
    languages: list[str]
    analyzer_config: AnalyzersConfigHelper
    dockerfile_path: str
    context_dir: str | Path
    pipeline_id: str
    image_name: str = "project-builder"
    project_path: str = "/tmp/my_project"
    force_rebuild: bool = False
    rebuild_images: bool = False
    version: SourceRevision | None = None
    log_level: str | None = None
    min_time_class: str = ""
    analyzers: list[str] = field(default_factory=list)
    additional_env: Mapping[str, str] = field(default_factory=dict)
    network: str | None = None
    bridge_client: BridgeClient | None = None
    agent_bridge_runtime_env: Mapping[str, str] | None = None
    base_image: str = ""
