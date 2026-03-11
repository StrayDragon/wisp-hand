from __future__ import annotations

from typing import Any, TypedDict

from pydantic import BaseModel, ConfigDict


class CapabilityResult(TypedDict):
    status: str
    version: str
    runtime_instance_id: str | None
    started_at: str | None
    transport: str
    host: str | None
    port: int | None
    paths: dict[str, str | None]
    paths_writable: dict[str, bool]
    retention: dict[str, Any]
    issues: list[dict[str, Any]]
    hyprland_detected: bool
    capture_available: bool
    input_available: bool
    vision_available: bool
    required_binaries: list[str]
    missing_binaries: list[str]
    optional_binaries: list[str]
    missing_optional: list[str]
    implemented_tools: list[str]
    config_path: str


class CapabilityResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    version: str
    runtime_instance_id: str | None = None
    started_at: str | None = None
    transport: str
    host: str | None = None
    port: int | None = None
    paths: dict[str, str | None]
    paths_writable: dict[str, bool]
    retention: dict[str, Any]
    issues: list[dict[str, Any]]
    hyprland_detected: bool
    capture_available: bool
    input_available: bool
    vision_available: bool
    required_binaries: list[str]
    missing_binaries: list[str]
    optional_binaries: list[str]
    missing_optional: list[str]
    implemented_tools: list[str]
    config_path: str
