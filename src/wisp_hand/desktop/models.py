from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BoundsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int
    y: int
    width: int
    height: int


class SizeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width: int
    height: int


class PixelRatioModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float
    y: float


class WorkspaceRefModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str


class WindowSummaryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    address: str
    class_: str = Field(alias="class", serialization_alias="class")
    title: str
    workspace: WorkspaceRefModel
    monitor: int
    at: list[int]
    size: list[int]


class ActiveWindowResultModel(WindowSummaryModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class MonitorSummaryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    layout_bounds: BoundsModel
    physical_size: SizeModel
    scale: float
    pixel_ratio: PixelRatioModel


class MonitorsResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    monitors: list[MonitorSummaryModel]


class WindowsListResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    windows: list[WindowSummaryModel]


class TopologyResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coordinate_backend: dict[str, Any]
    desktop_layout_bounds: BoundsModel
    monitors: list[dict[str, Any]]
    workspaces: list[dict[str, Any]]
    active_workspace: dict[str, Any]
    active_window: dict[str, Any]
    windows: list[dict[str, Any]] | None = None
    raw: dict[str, Any] | None = None


class CursorPositionResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int
    y: int
    scope_x: int
    scope_y: int
