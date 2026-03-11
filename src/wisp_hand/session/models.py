from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict

from wisp_hand.shared.types import JSONValue

ScopeType = Literal["desktop", "monitor", "window", "region", "window-follow-region"]


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


class SessionOpenResult(TypedDict):
    runtime_instance_id: str
    started_at: str
    session_id: str
    scope: ScopeEnvelope
    armed: bool
    dry_run: bool
    expires_at: str


class SessionCloseResult(TypedDict):
    session_id: str
    closed: bool
    closed_at: str


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


class SessionOpenResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_instance_id: str
    started_at: str
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
