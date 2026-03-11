from __future__ import annotations

from collections.abc import Callable
from typing import Any

from wisp_hand.coordinates.models import CoordinateMap
from wisp_hand.coordinates.service import CoordinateService
from wisp_hand.desktop.hyprland_adapter import HyprlandAdapter
from wisp_hand.session.store import SessionStore
from wisp_hand.shared.errors import WispHandError
from wisp_hand.shared.types import JSONValue

CoordinateResolvedCallback = Callable[[CoordinateMap], None]


class DesktopService:
    def __init__(
        self,
        *,
        session_store: SessionStore,
        hyprland: HyprlandAdapter,
        coordinates: CoordinateService,
        on_coordinates_resolved: CoordinateResolvedCallback | None = None,
    ) -> None:
        self._session_store = session_store
        self._hyprland = hyprland
        self._coordinates = coordinates
        self._on_coordinates_resolved = on_coordinates_resolved
        self._coordinates_last_fingerprint: str | None = None

    def resolve_topology_context(self, *, detail: str = "full") -> tuple[dict[str, Any], CoordinateMap]:
        topology = self._hyprland.get_topology(detail=detail)
        coordinate_map = self._resolve_coordinate_map(topology)
        return topology, coordinate_map

    def scope_bounds(
        self,
        scope: dict[str, JSONValue],
        topology: dict[str, Any],
        *,
        coordinate_map: CoordinateMap,
    ) -> dict[str, int]:
        return self._hyprland.scope_bounds(scope, topology, coordinate_map=coordinate_map)  # type: ignore[arg-type]

    def get_topology(self, *, detail: str = "summary") -> JSONValue:
        allowed = {"summary", "full", "raw"}
        if detail not in allowed:
            raise WispHandError(
                "invalid_parameters",
                "detail must be one of: summary, full, raw",
                {"detail": detail, "allowed": sorted(allowed)},
            )

        hypr_detail = "summary" if detail == "summary" else "full"
        raw_topology, coordinate_map = self.resolve_topology_context(detail=hypr_detail)
        augmented = self._augment_topology(topology=raw_topology, coordinate_map=coordinate_map)

        monitors = augmented.get("monitors")
        workspaces = augmented.get("workspaces")
        active_workspace = augmented.get("active_workspace")
        active_window = augmented.get("active_window")

        payload: dict[str, object] = {
            "coordinate_backend": augmented.get("coordinate_backend", {}),
            "desktop_layout_bounds": augmented.get("desktop_layout_bounds", {}),
            "monitors": [self._trim_monitor(item) for item in monitors] if isinstance(monitors, list) else [],
            "workspaces": [self._trim_workspace(item) for item in workspaces] if isinstance(workspaces, list) else [],
            "active_workspace": self._trim_workspace(active_workspace) if isinstance(active_workspace, dict) else {},
            "active_window": self._trim_window(active_window) if isinstance(active_window, dict) else {},
        }

        if detail in {"full", "raw"}:
            windows = augmented.get("windows")
            payload["windows"] = [self._trim_window(item) for item in windows] if isinstance(windows, list) else []

        if detail == "raw":
            payload["raw"] = raw_topology

        return payload  # type: ignore[return-value]

    def get_active_window(self) -> JSONValue:
        topology, _ = self.resolve_topology_context(detail="summary")
        active = topology.get("active_window")
        if not isinstance(active, dict):
            raise WispHandError(
                "capability_unavailable",
                "Hyprland active window payload is invalid",
                {"payload": active},
            )

        payload = self._trim_window_ref(active)
        required = {"address", "class", "title", "workspace", "monitor", "at", "size"}
        missing = sorted(required - set(payload))
        if missing:
            raise WispHandError(
                "capability_unavailable",
                "Hyprland active window payload is missing required fields",
                {"missing": missing, "payload": payload},
            )
        return payload

    def get_monitors(self) -> JSONValue:
        _, coordinate_map = self.resolve_topology_context(detail="summary")
        monitors = [
            {
                "name": monitor.name,
                "layout_bounds": monitor.layout_bounds.model_dump(),
                "physical_size": monitor.physical_size.model_dump(),
                "scale": monitor.scale,
                "pixel_ratio": monitor.pixel_ratio.model_dump(),
            }
            for monitor in coordinate_map.monitors
        ]
        return {"monitors": monitors}

    def list_windows(self, *, limit: int = 50) -> JSONValue:
        if not isinstance(limit, int):
            raise WispHandError("invalid_parameters", "limit must be an integer", {"limit": limit})
        if limit <= 0:
            raise WispHandError("invalid_parameters", "limit must be greater than zero", {"limit": limit})

        topology, _ = self.resolve_topology_context(detail="full")
        windows = topology.get("windows")
        if not isinstance(windows, list):
            raise WispHandError(
                "capability_unavailable",
                "Hyprland windows payload is invalid",
                {"payload": windows},
            )
        items: list[dict[str, object]] = []
        for window in windows:
            if not isinstance(window, dict):
                continue
            trimmed = self._trim_window_ref(window)
            required = {"address", "class", "title", "workspace", "monitor", "at", "size"}
            if required.issubset(trimmed):
                items.append(trimmed)
            if len(items) >= limit:
                break
        return {"windows": items}

    def get_cursor_position(self, *, session_id: str) -> JSONValue:
        session = self._session_store.get_session(session_id)
        topology, coordinate_map = self.resolve_topology_context()
        cursor = self._hyprland.get_cursor_position()
        relative = self._hyprland.relative_position(
            cursor=cursor,
            scope=session.scope,
            topology=topology,
            coordinate_map=coordinate_map,
        )
        return {
            "x": cursor["x"],
            "y": cursor["y"],
            "scope_x": relative["scope_x"],
            "scope_y": relative["scope_y"],
        }

    @staticmethod
    def _trim_monitor(value: object) -> object:
        if not isinstance(value, dict):
            return value
        allowed_keys = {
            "id",
            "name",
            "description",
            "focused",
            "x",
            "y",
            "width",
            "height",
            "layout_bounds",
            "physical_size",
            "scale",
            "pixel_ratio",
        }
        return {key: value[key] for key in allowed_keys if key in value}

    @staticmethod
    def _trim_workspace(value: object) -> object:
        if not isinstance(value, dict):
            return value
        allowed_keys = {"id", "name", "monitor", "windows", "hasfullscreen"}
        return {key: value[key] for key in allowed_keys if key in value}

    @staticmethod
    def _trim_workspace_ref(value: object) -> dict[str, object]:
        if not isinstance(value, dict):
            return {}
        allowed = {"id", "name"}
        return {key: value[key] for key in allowed if key in value}

    @classmethod
    def _trim_window_ref(cls, value: object) -> dict[str, object]:
        if not isinstance(value, dict):
            return {}
        allowed = {"address", "class", "title", "workspace", "monitor", "at", "size"}
        out: dict[str, object] = {key: value[key] for key in allowed if key in value}
        workspace = out.get("workspace")
        if isinstance(workspace, dict):
            out["workspace"] = cls._trim_workspace_ref(workspace)
        return out

    @classmethod
    def _trim_window(cls, value: object) -> object:
        return cls._trim_window_ref(value)

    def _resolve_coordinate_map(self, topology: dict[str, object]) -> CoordinateMap:
        coordinate_map = self._coordinates.resolve(topology)  # type: ignore[arg-type]
        if coordinate_map.topology_fingerprint != self._coordinates_last_fingerprint:
            self._coordinates_last_fingerprint = coordinate_map.topology_fingerprint
            if self._on_coordinates_resolved is not None:
                self._on_coordinates_resolved(coordinate_map)
        return coordinate_map

    @staticmethod
    def _augment_topology(*, topology: dict[str, object], coordinate_map: CoordinateMap) -> dict[str, object]:
        monitors = topology.get("monitors")
        mapped_by_name = {monitor.name: monitor for monitor in coordinate_map.monitors}
        if isinstance(monitors, list):
            enriched: list[object] = []
            for monitor in monitors:
                if isinstance(monitor, dict):
                    name = monitor.get("name")
                    mapped = mapped_by_name.get(name) if isinstance(name, str) else None
                    if mapped is not None:
                        enriched.append(
                            {
                                **monitor,
                                "layout_bounds": mapped.layout_bounds.model_dump(),
                                "physical_size": mapped.physical_size.model_dump(),
                                "scale": mapped.scale,
                                "pixel_ratio": mapped.pixel_ratio.model_dump(),
                            }
                        )
                        continue
                enriched.append(monitor)
            topology = {**topology, "monitors": enriched}

        return {
            **topology,
            "coordinate_backend": {
                "backend": coordinate_map.backend,
                "confidence": coordinate_map.confidence,
                "topology_fingerprint": coordinate_map.topology_fingerprint,
                "cached": coordinate_map.cached,
            },
            "desktop_layout_bounds": coordinate_map.desktop_layout_bounds.model_dump(),
        }
