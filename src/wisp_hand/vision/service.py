from __future__ import annotations

from typing import Any

from wisp_hand.capture.store import CaptureArtifactStore
from wisp_hand.infra.config import RuntimeConfig
from wisp_hand.shared.errors import WispHandError
from wisp_hand.vision.models import VisionDescribeResult, VisionLocateResult
from wisp_hand.vision.provider import (
    OllamaVisionProvider,
    PreparedVisionImage,
    prepare_capture_image,
    prepare_inline_image,
    scale_candidates,
)


class VisionService:
    def __init__(
        self,
        *,
        config: RuntimeConfig,
        capture_store: CaptureArtifactStore,
        vision_provider: OllamaVisionProvider | None,
    ) -> None:
        self._config = config
        self._capture_store = capture_store
        self._vision_provider = vision_provider

    def prepare_request(
        self,
        *,
        capture_id: str | None,
        inline_image: str | None,
    ) -> tuple[PreparedVisionImage, OllamaVisionProvider]:
        image = self._load_vision_image(capture_id=capture_id, inline_image=inline_image)
        provider = self._require_vision_provider()
        return image, provider

    def vision_describe(
        self,
        *,
        image: PreparedVisionImage,
        provider: OllamaVisionProvider,
        prompt: str | None = None,
    ) -> VisionDescribeResult:
        describe_prompt = prompt or "Describe the image concisely for an external computer-use agent."
        payload = provider.describe(image=image, prompt=describe_prompt)
        return {
            "provider": payload["provider"],
            "model": payload["model"],
            "input_source": image.input_source,
            "capture_id": image.capture_id,
            "image_width": image.width,
            "image_height": image.height,
            "processed_width": image.processed_width,
            "processed_height": image.processed_height,
            "answer": payload["answer"],
            "latency_ms": payload["latency_ms"],
        }

    def vision_locate(
        self,
        *,
        image: PreparedVisionImage,
        provider: OllamaVisionProvider,
        capture_id: str,
        target: str,
        limit: int = 3,
        space: str = "scope",
    ) -> VisionLocateResult:
        if not target:
            raise WispHandError("invalid_parameters", "target must not be empty")
        if not isinstance(limit, int):
            raise WispHandError("invalid_parameters", "limit must be an integer", {"limit": limit})
        if limit <= 0:
            raise WispHandError("invalid_parameters", "limit must be greater than zero", {"limit": limit})
        allowed_spaces = {"scope", "image", "both"}
        if not isinstance(space, str) or space not in allowed_spaces:
            raise WispHandError(
                "invalid_parameters",
                "space must be one of: scope, image, both",
                {"space": space, "allowed": sorted(allowed_spaces)},
            )

        payload = provider.locate(image=image, target=target)
        metadata = self._capture_store.load_metadata(capture_id)
        source_bounds = metadata.get("source_bounds") if isinstance(metadata, dict) else None
        pixel_ratio_x = metadata.get("pixel_ratio_x") if isinstance(metadata, dict) else None
        pixel_ratio_y = metadata.get("pixel_ratio_y") if isinstance(metadata, dict) else None

        raw_candidates = payload["candidates"][:limit]
        candidates_image = scale_candidates(
            candidates=raw_candidates,
            from_width=image.processed_width,
            from_height=image.processed_height,
            to_width=image.width,
            to_height=image.height,
        )
        candidates_scope: list[dict[str, object]] = []
        if (
            isinstance(source_bounds, dict)
            and isinstance(source_bounds.get("width"), int)
            and isinstance(source_bounds.get("height"), int)
            and isinstance(pixel_ratio_x, (int, float))
            and isinstance(pixel_ratio_y, (int, float))
            and pixel_ratio_x > 0
            and pixel_ratio_y > 0
        ):
            scope_width = int(source_bounds["width"])
            scope_height = int(source_bounds["height"])
            for candidate in candidates_image:
                sx = int(round(candidate["x"] / float(pixel_ratio_x)))
                sy = int(round(candidate["y"] / float(pixel_ratio_y)))
                sw = max(1, int(round(candidate["width"] / float(pixel_ratio_x))))
                sh = max(1, int(round(candidate["height"] / float(pixel_ratio_y))))
                sx = max(0, min(sx, scope_width - 1))
                sy = max(0, min(sy, scope_height - 1))
                sw = max(1, min(sw, scope_width - sx))
                sh = max(1, min(sh, scope_height - sy))
                candidates_scope.append(
                    {
                        "x": sx,
                        "y": sy,
                        "width": sw,
                        "height": sh,
                        "confidence": candidate["confidence"],
                        "reason": candidate["reason"],
                    }
                )

        result: dict[str, object] = {
            "provider": payload["provider"],
            "model": payload["model"],
            "input_source": image.input_source,
            "capture_id": capture_id,
            "image_width": image.width,
            "image_height": image.height,
            "processed_width": image.processed_width,
            "processed_height": image.processed_height,
            "target": target,
            "latency_ms": payload["latency_ms"],
        }
        if space in {"scope", "both"}:
            result["candidates_scope"] = candidates_scope
        if space in {"image", "both"}:
            result["candidates_image"] = candidates_image
        return result  # type: ignore[return-value]

    def _require_vision_provider(self) -> OllamaVisionProvider:
        if self._config.vision.mode != "assist":
            raise WispHandError(
                "capability_unavailable",
                "Vision mode is disabled",
                {"mode": self._config.vision.mode},
            )
        if self._vision_provider is None or not self._config.vision.model or not self._config.vision.base_url:
            raise WispHandError(
                "capability_unavailable",
                "Vision provider is not configured",
                {"mode": self._config.vision.mode},
            )
        return self._vision_provider

    def _load_vision_image(
        self,
        *,
        capture_id: str | None,
        inline_image: str | None,
    ) -> PreparedVisionImage:
        if (capture_id is None) == (inline_image is None):
            raise WispHandError(
                "invalid_parameters",
                "exactly one of capture_id or inline_image must be provided",
                {},
            )

        if capture_id is not None:
            return prepare_capture_image(
                artifact_store=self._capture_store,
                capture_id=capture_id,
                max_image_edge=self._config.vision.max_image_edge,
            )

        return prepare_inline_image(
            inline_image=str(inline_image),
            max_image_edge=self._config.vision.max_image_edge,
        )
