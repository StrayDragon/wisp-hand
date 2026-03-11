from __future__ import annotations

import math
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from PIL import Image

from wisp_hand.infra.command import CommandRunner
from wisp_hand.coordinates.fingerprint import topology_fingerprint
from wisp_hand.coordinates.models import (
    Bounds,
    CoordinateBackendId,
    CoordinateMap,
    MonitorMap,
    PhysicalSize,
    PixelRatio,
)
from wisp_hand.shared.errors import WispHandError

_SizeSemantics = Literal["layout", "physical"]


@dataclass(frozen=True, slots=True)
class _MonitorInput:
    name: str
    x: int
    y: int
    width: int
    height: int
    scale: float


def _parse_monitor_inputs(topology: dict[str, Any]) -> list[_MonitorInput]:
    monitors = topology.get("monitors")
    if not isinstance(monitors, list) or not monitors:
        raise WispHandError("capability_unavailable", "No monitor topology is available", {})

    parsed: list[_MonitorInput] = []
    for monitor in monitors:
        if not isinstance(monitor, dict):
            continue
        name = monitor.get("name")
        if not isinstance(name, str) or not name:
            raise WispHandError(
                "capability_unavailable",
                "Monitor payload is missing a name",
                {"payload": monitor},
            )
        x = monitor.get("x")
        y = monitor.get("y")
        width = monitor.get("width")
        height = monitor.get("height")
        scale = monitor.get("scale", 1.0)
        if not isinstance(x, int) or not isinstance(y, int):
            raise WispHandError(
                "capability_unavailable",
                "Monitor payload is missing x/y coordinates",
                {"monitor": name},
            )
        if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
            raise WispHandError(
                "capability_unavailable",
                "Monitor payload is missing width/height",
                {"monitor": name},
            )
        if isinstance(scale, int):
            scale_value = float(scale)
        elif isinstance(scale, float):
            scale_value = scale
        else:
            scale_value = 1.0
        if scale_value <= 0:
            scale_value = 1.0

        parsed.append(
            _MonitorInput(
                name=name,
                x=x,
                y=y,
                width=width,
                height=height,
                scale=scale_value,
            )
        )
    if not parsed:
        raise WispHandError("capability_unavailable", "No monitor topology is available", {})
    return parsed


def _layout_bounds_for(monitors: list[_MonitorInput], *, semantics: _SizeSemantics) -> list[Bounds]:
    bounds: list[Bounds] = []
    for monitor in monitors:
        if semantics == "layout":
            width = monitor.width
            height = monitor.height
        else:
            width = max(1, int(round(monitor.width / monitor.scale)))
            height = max(1, int(round(monitor.height / monitor.scale)))
        bounds.append(Bounds(x=monitor.x, y=monitor.y, width=width, height=height))
    return bounds


def _rects_overlap(a: Bounds, b: Bounds) -> bool:
    if a.x + a.width <= b.x or b.x + b.width <= a.x:
        return False
    if a.y + a.height <= b.y or b.y + b.height <= a.y:
        return False
    return True


def _edge_matches(bounds: list[Bounds]) -> int:
    matches = 0
    for i, a in enumerate(bounds):
        for j, b in enumerate(bounds):
            if i == j:
                continue
            # Horizontal adjacency with vertical overlap.
            vertical_overlap = not (a.y + a.height <= b.y or b.y + b.height <= a.y)
            if vertical_overlap and (a.x + a.width == b.x or b.x + b.width == a.x):
                matches += 1
            # Vertical adjacency with horizontal overlap.
            horizontal_overlap = not (a.x + a.width <= b.x or b.x + b.width <= a.x)
            if horizontal_overlap and (a.y + a.height == b.y or b.y + b.height == a.y):
                matches += 1
    return matches


def _hypothesis_score(bounds: list[Bounds]) -> tuple[int, int]:
    overlaps = 0
    for i, a in enumerate(bounds):
        for j, b in enumerate(bounds):
            if j <= i:
                continue
            if _rects_overlap(a, b):
                overlaps += 1
    matches = _edge_matches(bounds)
    return matches, overlaps


def _choose_semantics(monitors: list[_MonitorInput]) -> tuple[_SizeSemantics, float]:
    all_scales_1 = all(math.isclose(m.scale, 1.0, rel_tol=0.0, abs_tol=1e-6) for m in monitors)
    if all_scales_1:
        return "layout", 0.95
    if len(monitors) == 1:
        # Hyprland commonly reports monitor width/height in framebuffer (physical px) when scale != 1.0.
        return "physical", 0.6

    bounds_layout = _layout_bounds_for(monitors, semantics="layout")
    bounds_physical = _layout_bounds_for(monitors, semantics="physical")
    layout_matches, layout_overlaps = _hypothesis_score(bounds_layout)
    phys_matches, phys_overlaps = _hypothesis_score(bounds_physical)

    def score(matches: int, overlaps: int) -> int:
        return (matches * 2) - (overlaps * 10)

    layout_score = score(layout_matches, layout_overlaps)
    phys_score = score(phys_matches, phys_overlaps)

    if phys_score > layout_score:
        chosen = "physical"
        chosen_matches, chosen_overlaps = phys_matches, phys_overlaps
    else:
        chosen = "layout"
        chosen_matches, chosen_overlaps = layout_matches, layout_overlaps

    confidence = 0.55
    if chosen_overlaps == 0:
        confidence += 0.25
    if chosen_matches >= max(1, len(monitors) - 1):
        confidence += 0.15
    if abs(phys_score - layout_score) >= 5:
        confidence += 0.05
    return chosen, min(0.9, max(0.0, confidence))


def _desktop_bounds(bounds: list[Bounds]) -> Bounds:
    min_x = min(b.x for b in bounds)
    min_y = min(b.y for b in bounds)
    max_x = max(b.x + b.width for b in bounds)
    max_y = max(b.y + b.height for b in bounds)
    return Bounds(x=min_x, y=min_y, width=max(1, max_x - min_x), height=max(1, max_y - min_y))


def resolve_hyprctl_infer(topology: dict[str, Any]) -> CoordinateMap:
    monitors = _parse_monitor_inputs(topology)
    semantics, confidence = _choose_semantics(monitors)
    fingerprint = topology_fingerprint(topology)

    layout_bounds = _layout_bounds_for(monitors, semantics=semantics)
    desktop_layout_bounds = _desktop_bounds(layout_bounds)

    monitor_maps: list[MonitorMap] = []
    for monitor, bounds in zip(monitors, layout_bounds, strict=True):
        if semantics == "physical":
            physical_size = PhysicalSize(width=monitor.width, height=monitor.height)
        else:
            physical_size = PhysicalSize(
                width=max(1, int(round(bounds.width * monitor.scale))),
                height=max(1, int(round(bounds.height * monitor.scale))),
            )
        monitor_maps.append(
            MonitorMap(
                name=monitor.name,
                layout_bounds=bounds,
                physical_size=physical_size,
                scale=monitor.scale,
                pixel_ratio=PixelRatio(x=monitor.scale, y=monitor.scale),
                confidence=confidence,
            )
        )

    return CoordinateMap(
        backend="hyprctl-infer",
        confidence=confidence,
        topology_fingerprint=fingerprint,
        cached=False,
        desktop_layout_bounds=desktop_layout_bounds,
        monitors=monitor_maps,
    )


def resolve_grim_probe(
    topology: dict[str, Any],
    *,
    runner: CommandRunner,
    state_dir: Path,
    probe_region_size: int,
) -> CoordinateMap:
    base = resolve_hyprctl_infer(topology)
    if probe_region_size <= 0:
        raise WispHandError(
            "invalid_parameters",
            "probe_region_size must be greater than zero",
            {"probe_region_size": probe_region_size},
        )

    probe_dir = state_dir / "coordinates" / "probes"
    probe_dir.mkdir(parents=True, exist_ok=True)

    monitor_maps: list[MonitorMap] = []
    overall_confidence = 1.0
    for monitor in base.monitors:
        bounds = monitor.layout_bounds
        size = min(probe_region_size, bounds.width, bounds.height)
        size = max(1, int(size))
        probe_x = bounds.x + max(0, (bounds.width - size) // 2)
        probe_y = bounds.y + max(0, (bounds.height - size) // 2)
        geometry = f"{probe_x},{probe_y} {size}x{size}"

        try:
            tmp = tempfile.NamedTemporaryFile(prefix="grim-probe-", suffix=".png", dir=probe_dir, delete=False)
            tmp_path = Path(tmp.name)
            tmp.close()
            result = runner(["grim", "-g", geometry, str(tmp_path)])
        except FileNotFoundError as exc:
            raise WispHandError("dependency_missing", "Required binary is missing", {"binary": "grim"}) from exc
        finally:
            # tmp file might not exist when grim is missing.
            pass

        if result.returncode != 0:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise WispHandError(
                "capability_unavailable",
                "Grim probe failed",
                {"command": result.args, "stderr": result.stderr, "returncode": result.returncode},
            )

        try:
            with Image.open(tmp_path) as image:
                image_width = image.width
                image_height = image.height
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

        ratio_x = image_width / size
        ratio_y = image_height / size
        measured_scale = (ratio_x + ratio_y) / 2 if ratio_x > 0 and ratio_y > 0 else monitor.scale

        monitor_confidence = 0.97
        if abs(ratio_x - ratio_y) > 0.02:
            monitor_confidence -= 0.15
        if abs(measured_scale - monitor.scale) > 0.05:
            monitor_confidence -= 0.05
        monitor_confidence = max(0.0, min(1.0, monitor_confidence))
        overall_confidence = min(overall_confidence, monitor_confidence)

        monitor_maps.append(
            MonitorMap(
                name=monitor.name,
                layout_bounds=bounds,
                physical_size=PhysicalSize(
                    width=max(1, int(round(bounds.width * ratio_x))),
                    height=max(1, int(round(bounds.height * ratio_y))),
                ),
                scale=monitor.scale,
                pixel_ratio=PixelRatio(x=ratio_x, y=ratio_y),
                confidence=monitor_confidence,
            )
        )

    return CoordinateMap(
        backend="grim-probe",
        confidence=overall_confidence,
        topology_fingerprint=base.topology_fingerprint,
        cached=False,
        desktop_layout_bounds=base.desktop_layout_bounds,
        monitors=monitor_maps,
    )


def resolve_auto(
    topology: dict[str, Any],
    *,
    runner: CommandRunner,
    state_dir: Path,
    probe_region_size: int,
    min_confidence: float,
) -> CoordinateMap:
    inferred = resolve_hyprctl_infer(topology)
    has_scaling = any(not math.isclose(m.scale, 1.0, rel_tol=0.0, abs_tol=1e-6) for m in inferred.monitors)
    if inferred.confidence >= min_confidence and not has_scaling:
        return inferred

    try:
        probed = resolve_grim_probe(
            topology,
            runner=runner,
            state_dir=state_dir,
            probe_region_size=probe_region_size,
        )
    except WispHandError:
        return inferred

    return probed if probed.confidence >= inferred.confidence else inferred


def resolve_backend(
    topology: dict[str, Any],
    *,
    mode: Literal["auto", "hyprctl-infer", "grim-probe", "active-pointer-probe"],
    runner: CommandRunner,
    state_dir: Path,
    probe_region_size: int,
    min_confidence: float,
) -> CoordinateMap:
    if mode == "hyprctl-infer":
        return resolve_hyprctl_infer(topology)
    if mode == "grim-probe":
        return resolve_grim_probe(
            topology,
            runner=runner,
            state_dir=state_dir,
            probe_region_size=probe_region_size,
        )
    if mode == "auto":
        return resolve_auto(
            topology,
            runner=runner,
            state_dir=state_dir,
            probe_region_size=probe_region_size,
            min_confidence=min_confidence,
        )
    raise WispHandError(
        "invalid_config",
        "active-pointer-probe must be run via the diagnostic flow",
        {"mode": mode},
    )
