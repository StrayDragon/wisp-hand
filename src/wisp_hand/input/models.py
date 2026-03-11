from __future__ import annotations

from typing import Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict

from wisp_hand.session.models import ScopeEnvelope, ScopeEnvelopeModel
from wisp_hand.shared.types import JSONValue

PointerButton = Literal["left", "middle", "right"]
DispatchState = Literal["executed", "dry_run"]


class InputDispatchResult(TypedDict):
    session_id: str
    scope: ScopeEnvelope
    dispatch_state: DispatchState
    action: dict[str, JSONValue]


class InputDispatchResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    scope: ScopeEnvelopeModel
    dispatch_state: DispatchState
    action: dict[str, Any]
