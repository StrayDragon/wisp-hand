from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, NotRequired, TypeAlias, TypedDict

from pydantic import BaseModel, ConfigDict

JSONPrimitive: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]
ScopeType: TypeAlias = Literal[
    "desktop",
    "monitor",
    "window",
    "region",
    "window-follow-region",
]


class CoordinateSpace(TypedDict):
    origin: str
    units: str
    relative_to: str


class ScopeConstraints(TypedDict):
    input_relative: bool


class ScopeEnvelope(TypedDict):
    type: ScopeType
    target: JSONValue
    coordinate_space: CoordinateSpace
    constraints: ScopeConstraints


class CapabilityResult(TypedDict):
    hyprland_detected: bool
    capture_available: bool
    input_available: bool
    vision_available: bool
    required_binaries: list[str]
    missing_binaries: list[str]
    optional_binaries: list[str]
    implemented_tools: list[str]
    config_path: str


class SessionOpenResult(TypedDict):
    session_id: str
    scope: ScopeEnvelope
    armed: bool
    dry_run: bool
    expires_at: str


class SessionCloseResult(TypedDict):
    session_id: str
    closed: bool
    closed_at: str


class ErrorPayload(TypedDict):
    code: str
    message: str
    details: dict[str, JSONValue]


class AuditRecord(TypedDict):
    timestamp: str
    tool_name: str
    status: Literal["ok", "error"]
    latency_ms: int
    session_id: NotRequired[str | None]
    scope: NotRequired[ScopeEnvelope | None]
    result: NotRequired[JSONValue | None]
    error: NotRequired[ErrorPayload | None]


@dataclass(slots=True)
class SessionRecord:
    session_id: str
    scope: ScopeEnvelope
    armed: bool
    dry_run: bool
    created_at: datetime
    expires_at: datetime


class CoordinateSpaceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin: str
    units: str
    relative_to: str


class ScopeConstraintsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_relative: bool


class ScopeEnvelopeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ScopeType
    target: dict[str, Any]
    coordinate_space: CoordinateSpaceModel
    constraints: ScopeConstraintsModel


class CapabilityResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hyprland_detected: bool
    capture_available: bool
    input_available: bool
    vision_available: bool
    required_binaries: list[str]
    missing_binaries: list[str]
    optional_binaries: list[str]
    implemented_tools: list[str]
    config_path: str


class SessionOpenResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    scope: ScopeEnvelopeModel
    armed: bool
    dry_run: bool
    expires_at: str


class SessionCloseResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    closed: bool
    closed_at: str


class BoundsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int
    y: int
    width: int
    height: int


class TopologyResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    monitors: list[dict[str, Any]]
    workspaces: list[dict[str, Any]]
    active_workspace: dict[str, Any]
    active_window: dict[str, Any]
    windows: list[dict[str, Any]]


class CursorPositionResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int
    y: int
    scope_x: int
    scope_y: int


class CaptureResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capture_id: str
    scope: ScopeEnvelopeModel
    target: str
    width: int
    height: int
    mime_type: str
    path: str
    inline_base64: str | None = None
    created_at: str
    source_bounds: BoundsModel | None = None
    downscale: float | None = None
