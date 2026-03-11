from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any

from wisp_hand.infra.command import CommandResult, CommandRunner
from wisp_hand.coordinates.backends import resolve_hyprctl_infer
from wisp_hand.coordinates.models import CoordinateMap
from wisp_hand.shared.errors import WispHandError
from wisp_hand.session.models import ScopeEnvelope
from wisp_hand.shared.types import JSONValue


class HyprlandAdapter:
    def __init__(
        self,
        *,
        runner: CommandRunner | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._runner = runner or CommandRunner()
        self._env = env if env is not None else os.environ

    def get_topology(self, *, detail: str = "full") -> dict[str, Any]:
        self._ensure_supported_environment()
        topology: dict[str, Any] = {
            "monitors": self._query_json("monitors"),
            "workspaces": self._query_json("workspaces"),
            "active_workspace": self._query_json("activeworkspace"),
            "active_window": self._query_json("activewindow"),
        }
        if detail != "summary":
            topology["windows"] = self._query_json("clients")
        return topology

    def get_cursor_position(self) -> dict[str, int]:
        self._ensure_supported_environment()
        payload = self._query_json("cursorpos")
        if isinstance(payload, dict):
            x = payload.get("x")
            y = payload.get("y")
            if isinstance(x, int) and isinstance(y, int):
                return {"x": x, "y": y}
        raise WispHandError(
            "capability_unavailable",
            "Hyprland cursor payload is invalid",
            {"payload": payload},
        )

    def scope_bounds(
        self,
        scope: ScopeEnvelope,
        topology: dict[str, Any],
        *,
        coordinate_map: CoordinateMap | None = None,
    ) -> dict[str, int]:
        scope_type = scope["type"]
        target = scope["target"]

        if scope_type == "desktop":
            if coordinate_map is not None:
                return coordinate_map.desktop_layout_bounds.model_dump()
            return desktop_bounds(topology)
        if scope_type == "monitor":
            if coordinate_map is not None:
                selector = selector_value(target)
                for monitor in topology.get("monitors", []):
                    if matches_selector(monitor, selector):
                        name = monitor.get("name")
                        if isinstance(name, str):
                            for mapped in coordinate_map.monitors:
                                if mapped.name == name:
                                    return mapped.layout_bounds.model_dump()
                        break
            return monitor_bounds(topology, target)
        if scope_type == "window":
            return window_bounds(topology, target)
        if scope_type == "region":
            return normalize_bounds(target)
        if scope_type == "window-follow-region":
            if not isinstance(target, dict):
                raise WispHandError("invalid_scope", "window-follow-region target must be an object")
            window_box = window_bounds(topology, {"selector": target["window"]})
            region_box = normalize_bounds(target["region"])
            return {
                "x": window_box["x"] + region_box["x"],
                "y": window_box["y"] + region_box["y"],
                "width": region_box["width"],
                "height": region_box["height"],
            }
        raise WispHandError("invalid_scope", "Unsupported scope type", {"scope_type": scope_type})

    def relative_position(
        self,
        *,
        cursor: dict[str, int],
        scope: ScopeEnvelope,
        topology: dict[str, Any],
        coordinate_map: CoordinateMap | None = None,
    ) -> dict[str, int]:
        bounds = self.scope_bounds(scope, topology, coordinate_map=coordinate_map)
        return {
            "scope_x": cursor["x"] - bounds["x"],
            "scope_y": cursor["y"] - bounds["y"],
        }

    def _query_json(self, subcommand: str) -> Any:
        try:
            result = self._runner(["hyprctl", "-j", subcommand])
        except FileNotFoundError as exc:
            raise WispHandError(
                "dependency_missing",
                "Required binary is missing",
                {"binary": "hyprctl"},
            ) from exc

        self._ensure_command_succeeded(result)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise WispHandError(
                "capability_unavailable",
                "Hyprland command returned invalid JSON",
                {"command": result.args, "stdout": result.stdout},
            ) from exc

    def _ensure_supported_environment(self) -> None:
        if not self._env.get("HYPRLAND_INSTANCE_SIGNATURE"):
            raise WispHandError(
                "unsupported_environment",
                "Hyprland environment was not detected",
                {},
            )

    @staticmethod
    def _ensure_command_succeeded(result: CommandResult) -> None:
        if result.returncode != 0:
            raise WispHandError(
                "capability_unavailable",
                "Command execution failed",
                {
                    "command": result.args,
                    "stderr": result.stderr,
                    "returncode": result.returncode,
                },
            )


def desktop_bounds(topology: dict[str, Any]) -> dict[str, int]:
    coordinate_map = resolve_hyprctl_infer(topology)
    return coordinate_map.desktop_layout_bounds.model_dump()


def monitor_bounds(topology: dict[str, Any], target: JSONValue) -> dict[str, int]:
    selector = selector_value(target)
    for monitor in topology.get("monitors", []):
        if matches_selector(monitor, selector):
            name = monitor.get("name")
            if not isinstance(name, str) or not name:
                break
            coordinate_map = resolve_hyprctl_infer(topology)
            for monitor_map in coordinate_map.monitors:
                if monitor_map.name == name:
                    return monitor_map.layout_bounds.model_dump()
            break
    raise WispHandError("capability_unavailable", "Monitor selector did not match any known monitor", {"selector": selector})


def window_bounds(topology: dict[str, Any], target: JSONValue) -> dict[str, int]:
    selector = selector_value(target)
    for window in topology.get("windows", []):
        if matches_selector(window, selector):
            return normalize_bounds(window)
    active_window = topology.get("active_window")
    if isinstance(active_window, dict) and matches_selector(active_window, selector):
        return normalize_bounds(active_window)
    raise WispHandError("capability_unavailable", "Window selector did not match any known window", {"selector": selector})


def selector_value(target: JSONValue) -> JSONValue:
    if isinstance(target, dict) and "selector" in target:
        return target["selector"]
    return target


def matches_selector(payload: dict[str, Any], selector: JSONValue) -> bool:
    if selector is None:
        return False

    candidates = [
        payload.get("id"),
        payload.get("name"),
        payload.get("description"),
        payload.get("address"),
        payload.get("class"),
        payload.get("title"),
        payload.get("pid"),
    ]

    workspace = payload.get("workspace")
    if isinstance(workspace, dict):
        candidates.extend([workspace.get("id"), workspace.get("name")])

    return selector in candidates


def normalize_bounds(payload: JSONValue) -> dict[str, int]:
    if not isinstance(payload, dict):
        raise WispHandError("capability_unavailable", "Geometry payload is invalid", {"payload": payload})

    if all(key in payload for key in ("x", "y", "width", "height")):
        return {
            "x": int(payload["x"]),
            "y": int(payload["y"]),
            "width": int(payload["width"]),
            "height": int(payload["height"]),
        }

    at = payload.get("at")
    size = payload.get("size")
    if (
        isinstance(at, list)
        and len(at) == 2
        and isinstance(size, list)
        and len(size) == 2
    ):
        return {
            "x": int(at[0]),
            "y": int(at[1]),
            "width": int(size[0]),
            "height": int(size[1]),
        }

    raise WispHandError("capability_unavailable", "Geometry payload is missing bounds", {"payload": payload})
