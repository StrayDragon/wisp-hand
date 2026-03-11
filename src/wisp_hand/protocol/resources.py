from __future__ import annotations

import json
from uuid import UUID

from wisp_hand.capture import capture_metadata_uri, capture_png_uri
from wisp_hand.shared.errors import WispHandError


def normalize_capture_id(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise ValueError("invalid_parameters: capture_id must be a UUID") from exc


def register_resources(server) -> None:
    @server.mcp.resource(
        "wisp-hand://captures/{capture_id}.png",
        mime_type="image/png",
        title="Capture image",
        description="Capture artifact image stored by wisp_hand.capture.screen.",
    )
    def capture_png(capture_id: str) -> bytes:
        normalized = normalize_capture_id(capture_id)
        try:
            image_path = server.runtime._capture_store.resolve_image_path(normalized)  # pyright: ignore[reportPrivateUsage]
        except WispHandError as exc:
            raise ValueError(f"{exc.code}: {exc.message}") from exc
        return image_path.read_bytes()

    @server.mcp.resource(
        "wisp-hand://captures/{capture_id}.json",
        mime_type="application/json",
        title="Capture metadata",
        description="Capture artifact metadata stored by wisp_hand.capture.screen.",
    )
    def capture_metadata(capture_id: str) -> str:
        normalized = normalize_capture_id(capture_id)
        try:
            metadata = server.runtime._capture_store.load_metadata(normalized)  # pyright: ignore[reportPrivateUsage]
        except WispHandError as exc:
            raise ValueError(f"{exc.code}: {exc.message}") from exc
        return json.dumps(metadata, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
