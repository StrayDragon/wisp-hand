from __future__ import annotations

import base64
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from PIL import Image

from wisp_hand.command import CommandRunner
from wisp_hand.errors import WispHandError
from wisp_hand.hyprland import desktop_bounds
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
        bounds_resolver: Callable[[ScopeEnvelope, dict[str, Any]], dict[str, int]],
    ) -> dict[str, int] | None:
        if target == "desktop":
            return desktop_bounds(topology)
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
