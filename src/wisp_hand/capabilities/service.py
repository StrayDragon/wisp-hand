from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Mapping

from wisp_hand.capabilities.models import CapabilityResult


class DependencyProbe:
    def __init__(
        self,
        *,
        required_binaries: list[str],
        optional_binaries: list[str],
        binary_resolver: Callable[[str], str | None] | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._required_binaries = required_binaries
        self._optional_binaries = optional_binaries
        self._binary_resolver = binary_resolver or shutil.which
        self._env = env if env is not None else os.environ

    def report(self, *, config_path: str, implemented_tools: list[str]) -> CapabilityResult:
        missing_binaries = [
            name for name in self._required_binaries if self._binary_resolver(name) is None
        ]
        missing_optional = [
            name for name in self._optional_binaries if self._binary_resolver(name) is None
        ]
        hyprland_detected = bool(self._env.get("HYPRLAND_INSTANCE_SIGNATURE"))
        capture_available = (
            hyprland_detected and not missing_binaries and "wisp_hand.capture.screen" in implemented_tools
        )
        input_available = (
            hyprland_detected
            and not missing_binaries
            and "wtype" not in missing_optional
            and any(
                tool.startswith("wisp_hand.pointer.") or tool.startswith("wisp_hand.keyboard.")
                for tool in implemented_tools
            )
        )
        return {
            "hyprland_detected": hyprland_detected,
            "capture_available": capture_available,
            "input_available": input_available,
            "vision_available": False,
            "required_binaries": list(self._required_binaries),
            "missing_binaries": missing_binaries,
            "optional_binaries": list(self._optional_binaries),
            "missing_optional": missing_optional,
            "implemented_tools": list(implemented_tools),
            "config_path": config_path,
        }


class CapabilitiesService:
    def __init__(self, *, startup_discovery: CapabilityResult) -> None:
        self._startup_discovery = startup_discovery

    def capabilities(self) -> CapabilityResult:
        return dict(self._startup_discovery)
