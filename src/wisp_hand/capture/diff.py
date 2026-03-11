from __future__ import annotations

from typing import Any

from PIL import Image, ImageChops

from wisp_hand.capture.store import CaptureArtifactStore


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
