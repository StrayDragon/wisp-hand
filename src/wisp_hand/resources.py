from __future__ import annotations

from uuid import UUID


def capture_png_uri(capture_id: str) -> str:
    return f"wisp-hand://captures/{capture_id}.png"


def capture_metadata_uri(capture_id: str) -> str:
    return f"wisp-hand://captures/{capture_id}.json"


def normalize_capture_id(value: str) -> str:
    """
    Normalize capture ids for use in resource handlers.

    This also prevents path traversal because UUIDs cannot contain slashes.
    """
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise ValueError("invalid_parameters: capture_id must be a UUID") from exc

