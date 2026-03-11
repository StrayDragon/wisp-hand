from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

from pydantic import BaseModel, ConfigDict

VisionInputSource = Literal["capture", "inline"]


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
    candidates_scope: NotRequired[list[VisionLocateCandidate]]
    candidates_image: NotRequired[list[VisionLocateCandidate]]
    latency_ms: int


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
    candidates_scope: list[VisionLocateCandidateModel] | None = None
    candidates_image: list[VisionLocateCandidateModel] | None = None
    latency_ms: int
