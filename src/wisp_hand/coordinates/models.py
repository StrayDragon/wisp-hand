from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CoordinateBackendId = Literal["hyprctl-infer", "grim-probe", "active-pointer-probe"]


class Bounds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int
    y: int
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class PhysicalSize(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width: int = Field(gt=0)
    height: int = Field(gt=0)


class PixelRatio(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = Field(gt=0)
    y: float = Field(gt=0)


class MonitorMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    layout_bounds: Bounds
    physical_size: PhysicalSize
    scale: float = Field(gt=0)
    pixel_ratio: PixelRatio
    confidence: float = Field(ge=0.0, le=1.0)


class CoordinateBackendInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: CoordinateBackendId
    confidence: float = Field(ge=0.0, le=1.0)
    topology_fingerprint: str
    cached: bool


class CoordinateMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: CoordinateBackendId
    confidence: float = Field(ge=0.0, le=1.0)
    topology_fingerprint: str
    cached: bool
    desktop_layout_bounds: Bounds
    monitors: list[MonitorMap]

