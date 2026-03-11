from __future__ import annotations

import hashlib
import json
from typing import Any

from wisp_hand.shared.errors import WispHandError


def topology_fingerprint(topology: dict[str, Any]) -> str:
    monitors = topology.get("monitors")
    if not isinstance(monitors, list) or not monitors:
        raise WispHandError("capability_unavailable", "No monitor topology is available", {})

    normalized: list[dict[str, Any]] = []
    for monitor in monitors:
        if not isinstance(monitor, dict):
            continue
        normalized.append(
            {
                "name": monitor.get("name"),
                "description": monitor.get("description"),
                "x": monitor.get("x"),
                "y": monitor.get("y"),
                "width": monitor.get("width"),
                "height": monitor.get("height"),
                "scale": monitor.get("scale"),
                "transform": monitor.get("transform"),
                "refreshRate": monitor.get("refreshRate"),
            }
        )

    normalized.sort(key=lambda item: (str(item.get("name")), str(item.get("description"))))
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

