from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from wisp_hand.coordinates.models import CoordinateMap
from wisp_hand.errors import WispHandError


class CoordinateMapCache:
    def __init__(self, *, state_dir: Path) -> None:
        self._cache_dir = state_dir / "coordinates"
        self._cache_path = self._cache_dir / "coordinate_map.json"

    @property
    def path(self) -> Path:
        return self._cache_path

    def load(self, *, expected_fingerprint: str) -> CoordinateMap | None:
        if not self._cache_path.exists():
            return None
        try:
            payload = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):  # pragma: no cover - defensive
            return None
        if not isinstance(payload, dict):
            return None
        if payload.get("topology_fingerprint") != expected_fingerprint:
            return None
        try:
            cached = CoordinateMap.model_validate(payload)
        except ValidationError:
            return None
        return cached

    def save(self, coordinate_map: CoordinateMap) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            payload: dict[str, Any] = coordinate_map.model_dump(mode="json")
            self._cache_path.write_text(
                json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:  # pragma: no cover - defensive
            raise WispHandError(
                "capability_unavailable",
                "Failed to persist coordinate map cache",
                {"path": str(self._cache_path), "reason": str(exc)},
            ) from exc

