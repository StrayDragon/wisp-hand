from __future__ import annotations

import base64
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image

from wisp_hand.infra.command import CommandRunner
from wisp_hand.capture.models import CaptureTarget
from wisp_hand.capture.store import CaptureArtifactStore
from wisp_hand.coordinates.models import CoordinateMap
from wisp_hand.desktop.service import DesktopService
from wisp_hand.shared.errors import WispHandError
from wisp_hand.infra.config import RuntimeConfig
from wisp_hand.session.models import ScopeEnvelope
from wisp_hand.session.store import SessionStore


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
        runtime_instance_id: str | None = None,
        started_at: str | None = None,
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

        metadata_payload = {
            "capture_id": capture_id,
            "runtime_instance_id": runtime_instance_id,
            "started_at": started_at,
            "scope": scope,
            "target": target,
            "width": width,
            "height": height,
            "mime_type": "image/png",
            "created_at": created_at,
            "source_bounds": source_bounds,
            "source_coordinate_space": "layout_px",
            "image_coordinate_space": "image_px",
            "pixel_ratio_x": pixel_ratio_x,
            "pixel_ratio_y": pixel_ratio_y,
            "mapping": mapping,
            "downscale": downscale,
        }
        self._artifact_store.write_metadata(metadata_path=metadata_path, payload=metadata_payload)

        result_payload = dict(metadata_payload)
        if inline_base64 is not None:
            result_payload["inline_base64"] = inline_base64
        return result_payload

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


class CaptureService:
    def __init__(
        self,
        *,
        config: RuntimeConfig,
        session_store: SessionStore,
        desktop_service: DesktopService,
        capture_store: CaptureArtifactStore,
        capture_engine: CaptureEngine,
        capture_diff_engine,
        runtime_instance_id: str,
        started_at: str,
        now_provider: Callable[[], datetime],
        log_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self._config = config
        self._session_store = session_store
        self._desktop = desktop_service
        self._capture_store = capture_store
        self._capture_engine = capture_engine
        self._capture_diff_engine = capture_diff_engine
        self._runtime_instance_id = runtime_instance_id
        self._started_at = started_at
        self._now_provider = now_provider
        self._log_callback = log_callback

    def capture_screen(
        self,
        *,
        session_id: str,
        target: CaptureTarget,
        inline: bool = False,
        with_cursor: bool = False,
        downscale: float | None = None,
    ) -> dict[str, Any]:
        session = self._session_store.get_session(session_id)
        topology, coordinate_map = self._desktop.resolve_topology_context()
        result = self._capture_engine.capture(
            target=target,
            scope=session.scope,
            topology=topology,
            coordinate_map=coordinate_map,
            bounds_resolver=lambda scope, topology: self._desktop.scope_bounds(
                scope,
                topology,
                coordinate_map=coordinate_map,
            ),
            inline=inline,
            with_cursor=with_cursor,
            downscale=downscale,
            runtime_instance_id=self._runtime_instance_id,
            started_at=self._started_at,
        )
        capture_id = result.get("capture_id")
        if isinstance(capture_id, str):
            try:
                summary = self._capture_store.enforce_retention(
                    max_age_seconds=self._config.retention.captures.max_age_seconds,
                    max_total_bytes=self._config.retention.captures.max_total_bytes,
                    now=self._now_provider(),
                    exclude_capture_ids={capture_id},
                )
                if summary.get("removed_count") and self._log_callback is not None:
                    self._log_callback("capture.retention", summary)
            except Exception:
                pass
        return result

    def capture_diff(self, *, left_capture_id: str, right_capture_id: str) -> dict[str, Any]:
        return self._capture_diff_engine.diff(
            left_capture_id=left_capture_id,
            right_capture_id=right_capture_id,
        )
