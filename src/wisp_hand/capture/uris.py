from __future__ import annotations


def capture_png_uri(capture_id: str) -> str:
    return f"wisp-hand://captures/{capture_id}.png"


def capture_metadata_uri(capture_id: str) -> str:
    return f"wisp-hand://captures/{capture_id}.json"
