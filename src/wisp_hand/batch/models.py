from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

from pydantic import BaseModel, ConfigDict

from wisp_hand.session.models import ScopeEnvelope, ScopeEnvelopeModel
from wisp_hand.shared.errors import ErrorPayload, ErrorPayloadModel
from wisp_hand.shared.types import JSONValue

BatchStepStatus = Literal["ok", "error", "skipped"]
BatchReturnMode = Literal["summary", "full"]


class WaitResult(TypedDict):
    session_id: str
    duration_ms: int
    elapsed_ms: int


class BatchStepResult(TypedDict):
    index: int
    type: str
    status: BatchStepStatus
    output: NotRequired[JSONValue | None]
    error: NotRequired[ErrorPayload | None]


class BatchRunResult(TypedDict):
    batch_id: str
    return_mode: BatchReturnMode
    session_id: str
    scope: ScopeEnvelope
    stop_on_error: bool
    step_count: int
    steps: list[BatchStepResult]


class WaitResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    duration_ms: int
    elapsed_ms: int


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
    return_mode: BatchReturnMode
    session_id: str
    scope: ScopeEnvelopeModel
    stop_on_error: bool
    step_count: int
    steps: list[BatchStepResultModel]
