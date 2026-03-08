from __future__ import annotations

import base64
import json
from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from threading import BoundedSemaphore
from time import perf_counter
from typing import Any, Literal, Protocol
from urllib import error as urllib_error
from urllib import request as urllib_request

from PIL import Image

from wisp_hand.capture import CaptureArtifactStore
from wisp_hand.errors import WispHandError

VisionInputSource = Literal["capture", "inline"]


@dataclass(frozen=True, slots=True)
class PreparedVisionImage:
    input_source: VisionInputSource
    image_bytes: bytes
    width: int
    height: int
    processed_width: int
    processed_height: int
    capture_id: str | None = None


class OllamaTransport(Protocol):
    def __call__(self, *, url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]: ...


def prepare_capture_image(
    *,
    artifact_store: CaptureArtifactStore,
    capture_id: str,
    max_image_edge: int,
) -> PreparedVisionImage:
    metadata = artifact_store.load_metadata(capture_id)
    image_path = artifact_store.resolve_image_path(capture_id, metadata=metadata)
    return prepare_vision_image(
        image_bytes=image_path.read_bytes(),
        max_image_edge=max_image_edge,
        input_source="capture",
        capture_id=capture_id,
    )


def prepare_inline_image(*, inline_image: str, max_image_edge: int) -> PreparedVisionImage:
    try:
        image_bytes = base64.b64decode(inline_image, validate=True)
    except (ValueError, TypeError) as exc:
        raise WispHandError(
            "invalid_parameters",
            "inline_image must be valid base64",
            {},
        ) from exc

    return prepare_vision_image(
        image_bytes=image_bytes,
        max_image_edge=max_image_edge,
        input_source="inline",
    )


def prepare_vision_image(
    *,
    image_bytes: bytes,
    max_image_edge: int,
    input_source: VisionInputSource,
    capture_id: str | None = None,
) -> PreparedVisionImage:
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            normalized = image.convert("RGB")
            width = normalized.width
            height = normalized.height
            resized = normalized
            if max(width, height) > max_image_edge:
                scale = max_image_edge / max(width, height)
                resized = normalized.resize(
                    (
                        max(1, round(width * scale)),
                        max(1, round(height * scale)),
                    )
                )

            buffer = BytesIO()
            resized.save(buffer, format="PNG")
            return PreparedVisionImage(
                input_source=input_source,
                image_bytes=buffer.getvalue(),
                width=width,
                height=height,
                processed_width=resized.width,
                processed_height=resized.height,
                capture_id=capture_id,
            )
    except OSError as exc:
        raise WispHandError(
            "invalid_parameters",
            "image input could not be decoded",
            {"input_source": input_source},
        ) from exc


def scale_candidates(
    *,
    candidates: list[dict[str, Any]],
    from_width: int,
    from_height: int,
    to_width: int,
    to_height: int,
) -> list[dict[str, Any]]:
    if from_width <= 0 or from_height <= 0:
        raise WispHandError(
            "internal_error",
            "processed image dimensions must be positive",
            {},
        )

    scaled: list[dict[str, Any]] = []
    for candidate in candidates:
        x = int(candidate["x"] * to_width / from_width)
        y = int(candidate["y"] * to_height / from_height)
        width = max(1, int(candidate["width"] * to_width / from_width))
        height = max(1, int(candidate["height"] * to_height / from_height))
        clamped_x = max(0, min(x, to_width - 1))
        clamped_y = max(0, min(y, to_height - 1))
        scaled.append(
            {
                "x": clamped_x,
                "y": clamped_y,
                "width": max(1, min(width, to_width - clamped_x)),
                "height": max(1, min(height, to_height - clamped_y)),
                "confidence": candidate["confidence"],
                "reason": candidate["reason"],
            }
        )
    return scaled


class OllamaVisionProvider:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
        max_tokens: int,
        max_concurrency: int,
        transport: OllamaTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._max_tokens = max_tokens
        self._transport = transport or self._default_transport
        self._semaphore = BoundedSemaphore(max_concurrency)

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "ollama"

    def describe(
        self,
        *,
        image: PreparedVisionImage,
        prompt: str,
    ) -> dict[str, Any]:
        payload = self._request(
            prompt=prompt,
            image=image,
        )
        response = payload.get("response")
        if not isinstance(response, str):
            raise WispHandError(
                "capability_unavailable",
                "Ollama response is missing text output",
                {"provider": self.provider_name},
            )
        return {
            "provider": self.provider_name,
            "model": self._model,
            "answer": response.strip(),
            "latency_ms": payload["latency_ms"],
        }

    def locate(
        self,
        *,
        image: PreparedVisionImage,
        target: str,
    ) -> dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {
                "candidates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "integer"},
                            "y": {"type": "integer"},
                            "width": {"type": "integer"},
                            "height": {"type": "integer"},
                            "confidence": {"type": "number"},
                            "reason": {"type": "string"},
                        },
                        "required": ["x", "y", "width", "height", "confidence", "reason"],
                    },
                }
            },
            "required": ["candidates"],
        }
        prompt = (
            "Locate the requested UI target in the image. "
            f"Target: {target}. "
            f"Image size: {image.processed_width}x{image.processed_height}. "
            "Return JSON only. If the target cannot be found, return an empty candidates array."
        )
        payload = self._request(
            prompt=prompt,
            image=image,
            format_schema=schema,
        )

        structured = payload.get("response")
        if isinstance(structured, str):
            try:
                data = json.loads(structured)
            except json.JSONDecodeError as exc:
                raise WispHandError(
                    "capability_unavailable",
                    "Ollama response is not valid JSON",
                    {"provider": self.provider_name},
                ) from exc
        elif isinstance(structured, dict):
            data = structured
        else:
            raise WispHandError(
                "capability_unavailable",
                "Ollama response is missing structured locate output",
                {"provider": self.provider_name},
            )

        return {
            "provider": self.provider_name,
            "model": self._model,
            "candidates": self._normalize_candidates(data.get("candidates"), image=image),
            "latency_ms": payload["latency_ms"],
        }

    def _request(
        self,
        *,
        prompt: str,
        image: PreparedVisionImage,
        format_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self._base_url or not self._model:
            raise WispHandError(
                "capability_unavailable",
                "Vision provider is not configured",
                {},
            )

        body: dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
            "images": [base64.b64encode(image.image_bytes).decode("ascii")],
            "stream": False,
            "options": {"num_predict": self._max_tokens},
        }
        if format_schema is not None:
            body["format"] = format_schema

        started = perf_counter()
        self._semaphore.acquire()
        try:
            try:
                response = self._transport(
                    url=f"{self._base_url}/api/generate",
                    payload=body,
                    timeout=self._timeout_seconds,
                )
            except WispHandError:
                raise
            except (urllib_error.URLError, TimeoutError, OSError) as exc:
                raise WispHandError(
                    "capability_unavailable",
                    "Ollama provider is unavailable",
                    {"provider": self.provider_name, "reason": str(exc)},
                ) from exc
        finally:
            self._semaphore.release()

        return {
            **response,
            "latency_ms": max(0, round((perf_counter() - started) * 1000)),
        }

    def _default_transport(self, *, url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        request = urllib_request.Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8")
        except (urllib_error.URLError, TimeoutError, OSError) as exc:
            raise WispHandError(
                "capability_unavailable",
                "Ollama provider is unavailable",
                {"provider": self.provider_name, "reason": str(exc)},
            ) from exc

        try:
            payload_data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise WispHandError(
                "capability_unavailable",
                "Ollama provider returned invalid JSON",
                {"provider": self.provider_name},
            ) from exc

        if not isinstance(payload_data, dict):
            raise WispHandError(
                "capability_unavailable",
                "Ollama provider returned an invalid response payload",
                {"provider": self.provider_name},
            )
        return payload_data

    @staticmethod
    def _normalize_candidates(
        payload: Any,
        *,
        image: PreparedVisionImage,
    ) -> list[dict[str, Any]]:
        if not isinstance(payload, list):
            raise WispHandError(
                "capability_unavailable",
                "Ollama locate response is missing candidates",
                {"provider": "ollama"},
            )

        candidates: list[dict[str, Any]] = []
        for index, candidate in enumerate(payload):
            if not isinstance(candidate, dict):
                raise WispHandError(
                    "capability_unavailable",
                    "Ollama locate candidate is invalid",
                    {"candidate_index": index},
                )
            try:
                x = int(candidate["x"])
                y = int(candidate["y"])
                width = int(candidate["width"])
                height = int(candidate["height"])
                confidence = float(candidate["confidence"])
                reason = str(candidate["reason"])
            except (KeyError, TypeError, ValueError) as exc:
                raise WispHandError(
                    "capability_unavailable",
                    "Ollama locate candidate is malformed",
                    {"candidate_index": index},
                ) from exc

            candidates.append(
                {
                    "x": max(0, min(x, image.processed_width - 1)),
                    "y": max(0, min(y, image.processed_height - 1)),
                    "width": max(1, min(width, image.processed_width)),
                    "height": max(1, min(height, image.processed_height)),
                    "confidence": max(0.0, min(confidence, 1.0)),
                    "reason": reason,
                }
            )
        return candidates
