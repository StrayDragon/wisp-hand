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
PointerButton: TypeAlias = Literal["left", "middle", "right"]
DispatchState: TypeAlias = Literal["executed", "dry_run"]
BatchStepStatus: TypeAlias = Literal["ok", "error", "skipped"]


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


class InputDispatchResult(TypedDict):
    session_id: str
    scope: ScopeEnvelope
    dispatch_state: DispatchState
    action: dict[str, JSONValue]


class WaitResult(TypedDict):
    session_id: str
    duration_ms: int
    elapsed_ms: int


class CaptureDiffResult(TypedDict):
    left_capture_id: str
    right_capture_id: str
    changed: bool
    change_ratio: float
    changed_pixels: int
    total_pixels: int
    summary: str


class BatchStepResult(TypedDict):
    index: int
    type: str
    status: BatchStepStatus
    output: NotRequired[JSONValue | None]
    error: NotRequired["ErrorPayload" | None]


class BatchRunResult(TypedDict):
    batch_id: str
    session_id: str
    scope: ScopeEnvelope
    stop_on_error: bool
    step_count: int
    steps: list[BatchStepResult]


class VisionLocateCandidate(TypedDict):
    x: int
    y: int
    width: int
    height: int
    confidence: float
    reason: str


class VisionDescribeResult(TypedDict):
    provider: str
    model: str
    input_source: str
    capture_id: str | None
    image_width: int
    image_height: int
    processed_width: int
    processed_height: int
    answer: str
    latency_ms: int


class VisionLocateResult(TypedDict):
    provider: str
    model: str
    input_source: str
    capture_id: str
    image_width: int
    image_height: int
    processed_width: int
    processed_height: int
    target: str
    candidates_scope: list[VisionLocateCandidate]
    candidates_image: list[VisionLocateCandidate]
    latency_ms: int


class ErrorPayload(TypedDict):
    code: str
    message: str
    details: dict[str, JSONValue]


class AuditRecord(TypedDict):
    timestamp: str
    tool_name: str
    status: Literal["ok", "error", "denied"]
    latency_ms: int
    session_id: NotRequired[str | None]
    scope: NotRequired[ScopeEnvelope | None]
    result: NotRequired[JSONValue | None]
    error: NotRequired[ErrorPayload | None]
    batch_id: NotRequired[str | None]
    parent_tool_name: NotRequired[str | None]
    step_index: NotRequired[int | None]
    step_type: NotRequired[str | None]


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


class InputDispatchResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    scope: ScopeEnvelopeModel
    dispatch_state: DispatchState
    action: dict[str, Any]


class WaitResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    duration_ms: int
    elapsed_ms: int


class CaptureDiffResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left_capture_id: str
    right_capture_id: str
    changed: bool
    change_ratio: float
    changed_pixels: int
    total_pixels: int
    summary: str


class ErrorPayloadModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: dict[str, Any]


class BatchStepResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    type: str
    status: BatchStepStatus
    output: Any | None = None
    error: ErrorPayloadModel | None = None


class BatchRunResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: str
    session_id: str
    scope: ScopeEnvelopeModel
    stop_on_error: bool
    step_count: int
    steps: list[BatchStepResultModel]


class VisionLocateCandidateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int
    y: int
    width: int
    height: int
    confidence: float
    reason: str


class VisionDescribeResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    input_source: str
    capture_id: str | None
    image_width: int
    image_height: int
    processed_width: int
    processed_height: int
    answer: str
    latency_ms: int


class VisionLocateResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    input_source: str
    capture_id: str
    image_width: int
    image_height: int
    processed_width: int
    processed_height: int
    target: str
    candidates_scope: list[VisionLocateCandidateModel]
    candidates_image: list[VisionLocateCandidateModel]
    latency_ms: int


class BoundsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int
    y: int
    width: int
    height: int


class TopologyResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coordinate_backend: dict[str, Any]
    desktop_layout_bounds: BoundsModel
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
    source_coordinate_space: str
    image_coordinate_space: str
    pixel_ratio_x: float | None = None
    pixel_ratio_y: float | None = None
    mapping: dict[str, Any]
    downscale: float | None = None
