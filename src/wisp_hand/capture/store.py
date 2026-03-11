from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from wisp_hand.shared.errors import WispHandError


class CaptureArtifactStore:
    def __init__(self, *, base_dir: Path) -> None:
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def allocate(self) -> tuple[str, Path, Path]:
        capture_id = str(uuid4())
        image_path = self._base_dir / f"{capture_id}.png"
        metadata_path = self._base_dir / f"{capture_id}.json"
        return capture_id, image_path, metadata_path

    def write_metadata(self, *, metadata_path: Path, payload: dict[str, Any]) -> None:
        metadata_path.write_text(
            json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True),
            encoding="utf-8",
        )

    def load_metadata(self, capture_id: str) -> dict[str, Any]:
        metadata_path = self._base_dir / f"{capture_id}.json"
        if not metadata_path.exists():
            raise WispHandError("capability_unavailable", "Capture metadata could not be found", {"capture_id": capture_id})
        return json.loads(metadata_path.read_text(encoding="utf-8"))

    def resolve_image_path(self, capture_id: str, *, metadata: dict[str, Any] | None = None) -> Path:
        image_path = self._base_dir / f"{capture_id}.png"
        if not image_path.exists():
            raise WispHandError(
                "capability_unavailable",
                "Capture image could not be found",
                {"capture_id": capture_id},
            )
        return image_path

    def enforce_retention(
        self,
        *,
        max_age_seconds: int | None,
        max_total_bytes: int | None,
        now: datetime,
        exclude_capture_ids: set[str] | None = None,
    ) -> dict[str, Any]:
        """
        Best-effort capture retention enforcement.

        Requirements:
        - image + metadata MUST be kept or deleted as a pair
        - orphaned partial artifacts MUST be removed
        """
        exclude = exclude_capture_ids or set()

        png_files = {path.stem: path for path in self._base_dir.glob("*.png") if path.is_file()}
        json_files = {path.stem: path for path in self._base_dir.glob("*.json") if path.is_file()}
        all_ids = set(png_files) | set(json_files)

        def safe_unlink(path: Path) -> None:
            try:
                if path.exists():
                    path.unlink()
            except Exception:  # pragma: no cover - best-effort cleanup
                return

        # Remove orphaned artifacts first.
        orphaned = [cid for cid in all_ids if (cid in png_files) ^ (cid in json_files)]
        for cid in orphaned:
            if cid in exclude:
                continue
            if cid in png_files:
                safe_unlink(png_files[cid])
            if cid in json_files:
                safe_unlink(json_files[cid])

        # Collect valid capture entries.
        entries: list[tuple[str, datetime, int]] = []
        for cid in sorted(all_ids):
            if cid in exclude:
                continue
            png = png_files.get(cid)
            meta = json_files.get(cid)
            if png is None or meta is None:
                continue

            try:
                raw = json.loads(meta.read_text(encoding="utf-8"))
                created_at_raw = raw.get("created_at")
                created_at = (
                    datetime.fromisoformat(created_at_raw)
                    if isinstance(created_at_raw, str)
                    else datetime.fromtimestamp(meta.stat().st_mtime, tz=UTC)
                )
            except Exception:
                # If metadata can't be parsed, remove the pair to avoid half-broken artifacts.
                safe_unlink(png)
                safe_unlink(meta)
                continue

            try:
                size = png.stat().st_size + meta.stat().st_size
            except Exception:  # pragma: no cover - treat as zero-sized for budgeting
                size = 0

            entries.append((cid, created_at, size))

        removed_ids: list[str] = []
        removed_bytes = 0

        # Apply age budget.
        if max_age_seconds is not None:
            cutoff = now - timedelta(seconds=max_age_seconds)
            for cid, created_at, size in list(entries):
                if created_at < cutoff and cid not in exclude:
                    removed_ids.append(cid)
                    removed_bytes += size
                    entries.remove((cid, created_at, size))
                    png = png_files.get(cid)
                    meta = json_files.get(cid)
                    if png is not None:
                        safe_unlink(png)
                    if meta is not None:
                        safe_unlink(meta)

        # Apply total byte budget.
        if max_total_bytes is not None:
            entries.sort(key=lambda item: item[1])  # oldest first
            total = sum(size for _, _, size in entries)
            while entries and total > max_total_bytes:
                cid, _created_at, size = entries.pop(0)
                removed_ids.append(cid)
                removed_bytes += size
                total -= size
                png = png_files.get(cid)
                meta = json_files.get(cid)
                if png is not None:
                    safe_unlink(png)
                if meta is not None:
                    safe_unlink(meta)

        remaining_bytes = sum(size for _, _, size in entries)
        return {
            "removed_count": len(removed_ids),
            "removed_bytes": removed_bytes,
            "removed_ids": removed_ids,
            "remaining_count": len(entries),
            "remaining_bytes": remaining_bytes,
        }
