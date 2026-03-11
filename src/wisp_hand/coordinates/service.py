from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import sleep
from typing import Any

from wisp_hand.infra.command import CommandRunner
from wisp_hand.infra.config import CoordinatesConfig
from wisp_hand.coordinates.backends import resolve_backend, resolve_hyprctl_infer
from wisp_hand.coordinates.cache import CoordinateMapCache
from wisp_hand.coordinates.fingerprint import topology_fingerprint
from wisp_hand.coordinates.models import CoordinateMap
from wisp_hand.shared.errors import WispHandError
from wisp_hand.input.backend import InputBackend
from wisp_hand.desktop.hyprland_adapter import HyprlandAdapter


@dataclass(frozen=True, slots=True)
class ActiveProbeResult:
    coordinate_map: CoordinateMap
    expected: dict[str, int]
    observed: dict[str, int]
    error_px: int


class CoordinateService:
    def __init__(
        self,
        *,
        config: CoordinatesConfig,
        state_dir: Path,
        runner: CommandRunner,
    ) -> None:
        self._config = config
        self._cache = CoordinateMapCache(state_dir=state_dir)
        self._state_dir = state_dir
        self._runner = runner
        self._current: CoordinateMap | None = None

    def resolve(self, topology: dict[str, Any]) -> CoordinateMap:
        fingerprint = topology_fingerprint(topology)
        if self._current is not None and self._current.topology_fingerprint == fingerprint:
            return self._current

        if self._config.cache_enabled:
            cached = self._cache.load(expected_fingerprint=fingerprint)
            if cached is not None:
                resolved = cached.model_copy(update={"cached": True})
                self._current = resolved
                return resolved

        if self._config.mode == "active-pointer-probe":
            raise WispHandError(
                "invalid_config",
                "active-pointer-probe requires an explicit diagnostic flow",
                {"mode": self._config.mode},
            )

        resolved = resolve_backend(
            topology,
            mode=self._config.mode,
            runner=self._runner,
            state_dir=self._state_dir,
            probe_region_size=self._config.probe_region_size,
            min_confidence=self._config.min_confidence,
        )
        if self._config.cache_enabled:
            self._cache.save(resolved)

        self._current = resolved
        return resolved

    def run_active_pointer_probe(
        self,
        topology: dict[str, Any],
        *,
        hyprland: HyprlandAdapter,
        input_backend: InputBackend,
    ) -> ActiveProbeResult:
        if not self._config.active_probe_enabled:
            raise WispHandError(
                "policy_denied",
                "active pointer probe is disabled",
                {"active_probe_enabled": self._config.active_probe_enabled},
            )
        if self._config.active_probe_region is None:
            raise WispHandError(
                "invalid_config",
                "active_probe_region is required for active pointer probe",
                {},
            )

        region = self._config.active_probe_region
        expected = {
            "x": region.x + max(1, min(10, region.width - 1)),
            "y": region.y + max(1, min(10, region.height - 1)),
        }

        # Two hypotheses: use hyprctl inference as-is, and a second run after clearing cache state.
        # This is intentionally minimal; the primary value is validating extent and mapping end-to-end.
        candidate = resolve_hyprctl_infer(topology)
        desktop_bounds = candidate.desktop_layout_bounds.model_dump()

        original = hyprland.get_cursor_position()
        input_backend.move_pointer(
            x=int(expected["x"]),
            y=int(expected["y"]),
            desktop_bounds=desktop_bounds,
        )
        sleep(self._config.active_probe_move_delay_ms / 1000)
        observed = hyprland.get_cursor_position()

        error_px = abs(int(observed["x"]) - int(expected["x"])) + abs(int(observed["y"]) - int(expected["y"]))
        if error_px > self._config.active_probe_tolerance_px:
            # Best-effort restore to reduce surprise.
            try:
                input_backend.move_pointer(
                    x=int(original["x"]),
                    y=int(original["y"]),
                    desktop_bounds=desktop_bounds,
                )
            except Exception:
                pass
            raise WispHandError(
                "capability_unavailable",
                "Active pointer probe failed (cursor position mismatch)",
                {
                    "expected": expected,
                    "observed": observed,
                    "error_px": error_px,
                    "tolerance_px": self._config.active_probe_tolerance_px,
                },
            )

        # Restore pointer to original position.
        input_backend.move_pointer(
            x=int(original["x"]),
            y=int(original["y"]),
            desktop_bounds=desktop_bounds,
        )

        probed = candidate.model_copy(update={"backend": "active-pointer-probe", "confidence": 0.99})
        if self._config.cache_enabled:
            self._cache.save(probed)
        self._current = probed

        return ActiveProbeResult(
            coordinate_map=probed,
            expected=expected,
            observed=observed,
            error_px=error_px,
        )

