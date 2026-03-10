from __future__ import annotations

import base64
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from PIL import Image, ImageChops

from wisp_hand.command import CommandRunner
from wisp_hand.coordinates.models import CoordinateMap
from wisp_hand.errors import WispHandError
from wisp_hand.models import ScopeEnvelope

CaptureTarget = Literal["scope", "desktop", "monitor", "window", "region"]


class CaptureArtifactStore:
    def __init__(self, *, base_dir: Path) -> None:
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def allocate(self) -> tuple[str, Path, Path]:
        capture_id = str(uuid4())
        image_path = self._base_dir / f"{capture_id}.png"
        metadata_path = self._base_dir / f"{capture_id}.json"
        return capture_id, image_path, metadata_path

    def write_metadata(self, *, metadata_path: Path, payload: dict[str, Any]) -> None:
        metadata_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")

    def load_metadata(self, capture_id: str) -> dict[str, Any]:
        metadata_path = self._base_dir / f"{capture_id}.json"
        if not metadata_path.exists():
            raise WispHandError("capability_unavailable", "Capture metadata could not be found", {"capture_id": capture_id})
        return json.loads(metadata_path.read_text(encoding="utf-8"))

    def resolve_image_path(self, capture_id: str, *, metadata: dict[str, Any] | None = None) -> Path:
        payload = metadata if metadata is not None else self.load_metadata(capture_id)
        raw_path = payload.get("path")
        if not isinstance(raw_path, str):
            raise WispHandError(
                "capability_unavailable",
                "Capture metadata is missing an image path",
                {"capture_id": capture_id},
            )
        image_path = Path(raw_path)
        if not image_path.exists():
            raise WispHandError(
                "capability_unavailable",
                "Capture image could not be found",
                {"capture_id": capture_id, "path": raw_path},
            )
        return image_path


class CaptureEngine:
    def __init__(
        self,
        *,
        artifact_store: CaptureArtifactStore,
        runner: CommandRunner | None = None,
        binary_resolver: Callable[[str], str | None] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._artifact_store = artifact_store
        self._runner = runner or CommandRunner()
        self._binary_resolver = binary_resolver
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def capture(
        self,
        *,
        target: CaptureTarget,
        scope: ScopeEnvelope,
        topology: dict[str, Any],
        coordinate_map: CoordinateMap,
        bounds_resolver: Callable[[ScopeEnvelope, dict[str, Any]], dict[str, int]],
        inline: bool,
        with_cursor: bool,
        downscale: float | None,
    ) -> dict[str, Any]:
        self._ensure_backend_available()
        capture_id, image_path, metadata_path = self._artifact_store.allocate()
        source_bounds = self._resolve_bounds(
            target=target,
            scope=scope,
            topology=topology,
            coordinate_map=coordinate_map,
            bounds_resolver=bounds_resolver,
        )

        command = ["grim"]
        if with_cursor:
            command.append("-c")
        if source_bounds is not None:
            command.extend(["-g", self._geometry_string(source_bounds)])
        command.append(str(image_path))

        try:
            result = self._runner(command)
        except FileNotFoundError as exc:
            raise WispHandError("dependency_missing", "Required binary is missing", {"binary": "grim"}) from exc

        if result.returncode != 0:
            raise WispHandError(
                "capability_unavailable",
                "Screenshot capture failed",
                {
                    "command": result.args,
                    "stderr": result.stderr,
                    "returncode": result.returncode,
                },
            )

        width, height = self._maybe_downscale(image_path, downscale)
        image_bytes = image_path.read_bytes()
        inline_base64 = base64.b64encode(image_bytes).decode("ascii") if inline else None
        created_at = self._now_provider().isoformat()

        mapping = self._build_mapping(source_bounds=source_bounds, coordinate_map=coordinate_map)
        pixel_ratio_x: float | None
        pixel_ratio_y: float | None
        if mapping["kind"] == "single":
            pixel_ratio_x = width / source_bounds["width"]
            pixel_ratio_y = height / source_bounds["height"]
        else:
            pixel_ratio_x = None
            pixel_ratio_y = None

        payload = {
            "capture_id": capture_id,
            "scope": scope,
            "target": target,
            "width": width,
            "height": height,
            "mime_type": "image/png",
            "path": str(image_path),
            "inline_base64": inline_base64,
            "created_at": created_at,
            "source_bounds": source_bounds,
            "source_coordinate_space": "layout_px",
            "image_coordinate_space": "image_px",
            "pixel_ratio_x": pixel_ratio_x,
            "pixel_ratio_y": pixel_ratio_y,
            "mapping": mapping,
            "downscale": downscale,
        }
        self._artifact_store.write_metadata(metadata_path=metadata_path, payload=payload)
        return payload

    def _ensure_backend_available(self) -> None:
        if self._binary_resolver is None:
            return
        if self._binary_resolver("grim") is None:
            raise WispHandError("dependency_missing", "Required binary is missing", {"binary": "grim"})

    def _resolve_bounds(
        self,
        *,
        target: CaptureTarget,
        scope: ScopeEnvelope,
        topology: dict[str, Any],
        coordinate_map: CoordinateMap,
        bounds_resolver: Callable[[ScopeEnvelope, dict[str, Any]], dict[str, int]],
    ) -> dict[str, int] | None:
        if target == "desktop":
            return coordinate_map.desktop_layout_bounds.model_dump()
        if target == "scope":
            return bounds_resolver(scope, topology)
        if target == "monitor" and scope["type"] == "monitor":
            return bounds_resolver(scope, topology)
        if target == "window" and scope["type"] in {"window", "window-follow-region"}:
            if scope["type"] == "window":
                return bounds_resolver(scope, topology)
            return bounds_resolver(
                {
                    "type": "window",
                    "target": {"selector": scope["target"]["window"]},
                    "coordinate_space": scope["coordinate_space"],
                    "constraints": scope["constraints"],
                },
                topology,
            )
        if target == "region" and scope["type"] in {"region", "window-follow-region"}:
            if scope["type"] == "region":
                return bounds_resolver(scope, topology)
            return bounds_resolver(
                {
                    "type": "region",
                    "target": scope["target"]["region"],
                    "coordinate_space": scope["coordinate_space"],
                    "constraints": scope["constraints"],
                },
                topology,
            )

        raise WispHandError(
            "invalid_parameters",
            "Capture target is incompatible with the current session scope",
            {
                "target": target,
                "scope_type": scope["type"],
            },
        )

    @staticmethod
    def _build_mapping(*, source_bounds: dict[str, int], coordinate_map: CoordinateMap) -> dict[str, Any]:
        involved: list[dict[str, Any]] = []
        ratios: list[tuple[float, float]] = []

        sx = source_bounds["x"]
        sy = source_bounds["y"]
        sx2 = sx + source_bounds["width"]
        sy2 = sy + source_bounds["height"]

        for monitor in coordinate_map.monitors:
            bounds = monitor.layout_bounds
            mx1 = bounds.x
            my1 = bounds.y
            mx2 = mx1 + bounds.width
            my2 = my1 + bounds.height
            ix1 = max(sx, mx1)
            iy1 = max(sy, my1)
            ix2 = min(sx2, mx2)
            iy2 = min(sy2, my2)
            if ix2 <= ix1 or iy2 <= iy1:
                continue
            involved.append(
                {
                    "name": monitor.name,
                    "layout_bounds": bounds.model_dump(),
                    "pixel_ratio": monitor.pixel_ratio.model_dump(),
                }
            )
            ratios.append((monitor.pixel_ratio.x, monitor.pixel_ratio.y))

        if not involved:
            return {"kind": "unknown", "monitors": []}

        first = ratios[0]
        uniform = all(abs(rx - first[0]) <= 1e-3 and abs(ry - first[1]) <= 1e-3 for rx, ry in ratios[1:])
        kind = "single" if uniform else "multi-monitor"
        return {"kind": kind, "monitors": involved}

    @staticmethod
    def _geometry_string(bounds: dict[str, int]) -> str:
        return f"{bounds['x']},{bounds['y']} {bounds['width']}x{bounds['height']}"

    @staticmethod
    def _maybe_downscale(image_path: Path, downscale: float | None) -> tuple[int, int]:
        with Image.open(image_path) as image:
            if downscale is None:
                return image.width, image.height
            if downscale <= 0 or downscale > 1:
                raise WispHandError(
                    "invalid_parameters",
                    "downscale must be greater than 0 and less than or equal to 1",
                    {"downscale": downscale},
                )
            resized = image.resize(
                (
                    max(1, round(image.width * downscale)),
                    max(1, round(image.height * downscale)),
                )
            )
            resized.save(image_path, format="PNG")
            return resized.width, resized.height


class CaptureDiffEngine:
    def __init__(self, *, artifact_store: CaptureArtifactStore) -> None:
        self._artifact_store = artifact_store

    def diff(self, *, left_capture_id: str, right_capture_id: str) -> dict[str, Any]:
        left_metadata = self._artifact_store.load_metadata(left_capture_id)
        right_metadata = self._artifact_store.load_metadata(right_capture_id)
        left_path = self._artifact_store.resolve_image_path(left_capture_id, metadata=left_metadata)
        right_path = self._artifact_store.resolve_image_path(right_capture_id, metadata=right_metadata)

        with Image.open(left_path) as left_image, Image.open(right_path) as right_image:
            left_rgba = left_image.convert("RGBA")
            right_rgba = right_image.convert("RGBA")
            canvas_width = max(left_rgba.width, right_rgba.width)
            canvas_height = max(left_rgba.height, right_rgba.height)
            left_canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
            right_canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
            left_canvas.paste(left_rgba, (0, 0))
            right_canvas.paste(right_rgba, (0, 0))
            diff_image = ImageChops.difference(left_canvas, right_canvas)
            bbox = diff_image.convert("RGB").getbbox()
            changed_pixels = sum(1 for pixel in diff_image.getdata() if pixel != (0, 0, 0, 0))

        total_pixels = canvas_width * canvas_height
        change_ratio = 0.0 if total_pixels == 0 else round(changed_pixels / total_pixels, 6)
        changed = changed_pixels > 0

        if bbox is None:
            summary = f"No pixel changes detected across {canvas_width}x{canvas_height}"
        else:
            x1, y1, x2, y2 = bbox
            summary = (
                f"{changed_pixels}/{total_pixels} pixels changed "
                f"({change_ratio:.6f}) within bbox {x1},{y1} {x2 - x1}x{y2 - y1}"
            )

        return {
            "left_capture_id": left_capture_id,
            "right_capture_id": right_capture_id,
            "changed": changed,
            "change_ratio": change_ratio,
            "changed_pixels": changed_pixels,
            "total_pixels": total_pixels,
            "summary": summary,
        }
