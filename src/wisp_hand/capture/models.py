from __future__ import annotations

from typing import Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict

from wisp_hand.session.models import ScopeEnvelopeModel

CaptureTarget = Literal["scope", "desktop", "monitor", "window", "region"]


class CaptureDiffResult(TypedDict):
    left_capture_id: str
    right_capture_id: str
    changed: bool
    change_ratio: float
    changed_pixels: int
    total_pixels: int
    summary: str


class CaptureDiffResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left_capture_id: str
    right_capture_id: str
    changed: bool
    change_ratio: float
    changed_pixels: int
    total_pixels: int
    summary: str


class BoundsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int
    y: int
    width: int
    height: int


class CaptureResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capture_id: str
    runtime_instance_id: str | None = None
    started_at: str | None = None
    scope: ScopeEnvelopeModel
    target: str
    width: int
    height: int
    mime_type: str
    inline_base64: str | None = None
    created_at: str
    image_uri: str
    metadata_uri: str
    source_bounds: BoundsModel | None = None
    source_coordinate_space: str
    image_coordinate_space: str
    pixel_ratio_x: float | None = None
    pixel_ratio_y: float | None = None
    mapping: dict[str, Any]
    downscale: float | None = None
