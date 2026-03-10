from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wisp_hand.config import load_runtime_config
from wisp_hand.errors import WispHandError
from wisp_hand.runtime import WispHandRuntime


@dataclass(frozen=True, slots=True)
class Region:
    x: int
    y: int
    width: int
    height: int


def _region_from_string(value: str) -> Region:
    parts = value.split(",")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("region must be x,y,width,height")
    try:
        x, y, width, height = (int(part.strip()) for part in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("region must be integers") from exc
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("region width/height must be positive")
    return Region(x=x, y=y, width=width, height=height)


def _binary_path(name: str) -> str | None:
    path = shutil.which(name)
    return path if path else None


def _write_runtime_config(
    *,
    config_path: Path,
    state_dir: Path,
    coordinates: dict[str, Any],
) -> None:
    lines: list[str] = [
        "[server]",
        'transport = "stdio"',
        "",
        "[paths]",
        f'state_dir = "{state_dir.as_posix()}"',
        f'audit_file = "{(state_dir / "audit.jsonl").as_posix()}"',
        f'runtime_log_file = "{(state_dir / "runtime.jsonl").as_posix()}"',
        f'capture_dir = "{(state_dir / "captures").as_posix()}"',
        "",
        "[logging]",
        'level = "INFO"',
        "allow_sensitive = false",
        "",
        "[logging.console]",
        "enabled = false",
        'format = "plain"',
        "",
        "[logging.file]",
        "enabled = true",
        'format = "json"',
        "",
        "[session]",
        "default_ttl_seconds = 60",
        "max_ttl_seconds = 300",
        "",
        "[coordinates]",
        f'mode = "{coordinates["mode"]}"',
        f'cache_enabled = {str(bool(coordinates["cache_enabled"])).lower()}',
        f"probe_region_size = {int(coordinates['probe_region_size'])}",
        f"min_confidence = {float(coordinates['min_confidence'])}",
        f'active_probe_enabled = {str(bool(coordinates.get("active_probe_enabled", False))).lower()}',
        f"active_probe_tolerance_px = {int(coordinates.get('active_probe_tolerance_px', 2))}",
        f"active_probe_move_delay_ms = {int(coordinates.get('active_probe_move_delay_ms', 50))}",
        "",
    ]

    active_region = coordinates.get("active_probe_region")
    if isinstance(active_region, Region):
        lines.extend(
            [
                "[coordinates.active_probe_region]",
                f"x = {active_region.x}",
                f"y = {active_region.y}",
                f"width = {active_region.width}",
                f"height = {active_region.height}",
                "",
            ]
        )

    config_path.write_text("\n".join(lines), encoding="utf-8")


def _pick_probe_region(*, monitor_layout: dict[str, Any], size: int) -> Region:
    x = int(monitor_layout.get("x", 0))
    y = int(monitor_layout.get("y", 0))
    width = int(monitor_layout.get("width", size))
    height = int(monitor_layout.get("height", size))
    w = min(size, width)
    h = min(size, height)
    cx = x + max(0, (width - w) // 2)
    cy = y + max(0, (height - h) // 2)
    return Region(x=cx, y=cy, width=max(1, w), height=max(1, h))


@contextlib.contextmanager
def _maybe_temp_state_dir(state_dir: Path | None):
    if state_dir is not None:
        state_dir.mkdir(parents=True, exist_ok=True)
        yield state_dir
        return
    with tempfile.TemporaryDirectory(prefix="wisp-hand-coordinates-") as temp_root:
        root = Path(temp_root)
        state = root / "state"
        state.mkdir(parents=True, exist_ok=True)
        yield state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="diagnose_coordinates",
        epilog=(
            "Active pointer probe (diagnostic-only):\n"
            "  1) Select a safe region using slurp:\n"
            "     REGION=\"$(slurp -f '%x,%y,%w,%h')\"\n"
            "  2) Run active probe (moves pointer; requires explicit confirmation):\n"
            "     uv run python examples/attempts/diagnose_coordinates.py "
            "--active-probe --confirm-active-probe --active-probe-region \"$REGION\"\n"
            "\n"
            "If clicks are offset on fractional scaling, prefer mode=auto (will use grim-probe) "
            "and keep capture scopes inside a single monitor."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--out", type=Path, help="Write JSON report to this path (defaults to stdout).")
    parser.add_argument("--state-dir", type=Path, help="Persist state dir (enables cache reuse across runs).")
    parser.add_argument(
        "--mode",
        choices=["auto", "hyprctl-infer", "grim-probe"],
        default="auto",
        help="Coordinate backend selection mode.",
    )
    parser.add_argument("--no-cache", action="store_true", help="Disable coordinate map cache.")
    parser.add_argument("--probe-region-size", type=int, default=120, help="Probe region size for grim-probe.")
    parser.add_argument("--min-confidence", type=float, default=0.75, help="Minimum confidence before probing.")
    parser.add_argument(
        "--capture-check",
        action="store_true",
        help="Run per-monitor capture checks to validate pixel_ratio vs capture output.",
    )
    parser.add_argument("--capture-region-size", type=int, default=120, help="Region size for capture check.")
    parser.add_argument("--active-probe", action="store_true", help="Run active pointer probe (has side effects).")
    parser.add_argument(
        "--confirm-active-probe",
        action="store_true",
        help="Required to run --active-probe.",
    )
    parser.add_argument(
        "--active-probe-region",
        type=_region_from_string,
        help="Safe region for active probe as x,y,width,height (layout px).",
    )
    args = parser.parse_args(argv)

    report: dict[str, Any] = {
        "progress": {"phase": "init", "updated_at": time.time()},
        "env": {
            "HYPRLAND_INSTANCE_SIGNATURE": os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"),
            "WAYLAND_DISPLAY": os.environ.get("WAYLAND_DISPLAY"),
            "XDG_SESSION_TYPE": os.environ.get("XDG_SESSION_TYPE"),
        },
        "binaries": {
            "hyprctl": _binary_path("hyprctl"),
            "grim": _binary_path("grim"),
            "slurp": _binary_path("slurp"),
            "wtype": _binary_path("wtype"),
        },
        "coordinates": {
            "mode": args.mode,
            "cache_enabled": not args.no_cache,
            "probe_region_size": args.probe_region_size,
            "min_confidence": args.min_confidence,
        },
        "checks": {},
    }

    def write_out() -> None:
        payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.out is None:
            print(payload, end="")
            return
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")

    with _maybe_temp_state_dir(args.state_dir) as state_dir:
        config_path = state_dir / "config.toml"
        coordinates = dict(report["coordinates"])
        if args.active_probe:
            if not args.confirm_active_probe:
                report["checks"]["active_probe"] = {
                    "ok": False,
                    "error": "missing --confirm-active-probe",
                }
                write_out()
                return 2
            if args.active_probe_region is None:
                report["checks"]["active_probe"] = {"ok": False, "error": "missing --active-probe-region"}
                write_out()
                return 2
            coordinates["active_probe_enabled"] = True
            coordinates["active_probe_region"] = args.active_probe_region

        _write_runtime_config(
            config_path=config_path,
            state_dir=state_dir,
            coordinates=coordinates,
        )
        runtime = WispHandRuntime(config=load_runtime_config(config_path))

        report["progress"] = {"phase": "topology", "updated_at": time.time()}
        try:
            topology = runtime.get_topology()
            report["checks"]["topology"] = {"ok": True, "value": topology}
        except WispHandError as exc:
            report["checks"]["topology"] = {"ok": False, "error": exc.to_payload()}
            write_out()
            return 1

        if args.capture_check and isinstance(topology, dict):
            report["progress"] = {"phase": "capture_check", "updated_at": time.time()}
            results: list[dict[str, Any]] = []
            monitors = topology.get("monitors")
            for monitor in monitors if isinstance(monitors, list) else []:
                if not isinstance(monitor, dict):
                    continue
                name = monitor.get("name")
                layout = monitor.get("layout_bounds")
                if not isinstance(layout, dict):
                    continue
                region = _pick_probe_region(monitor_layout=layout, size=args.capture_region_size)
                opened = runtime.open_session(
                    scope_type="region",
                    scope_target={
                        "x": region.x,
                        "y": region.y,
                        "width": region.width,
                        "height": region.height,
                    },
                    armed=False,
                    dry_run=False,
                    ttl_seconds=60,
                )
                try:
                    capture = runtime.capture_screen(session_id=opened["session_id"], target="scope", inline=False)
                    results.append(
                        {
                            "monitor": name,
                            "region": {
                                "x": region.x,
                                "y": region.y,
                                "width": region.width,
                                "height": region.height,
                            },
                            "capture_id": capture.get("capture_id") if isinstance(capture, dict) else None,
                            "captured_size": {
                                "width": capture.get("width") if isinstance(capture, dict) else None,
                                "height": capture.get("height") if isinstance(capture, dict) else None,
                            },
                            "pixel_ratio": {
                                "x": capture.get("pixel_ratio_x") if isinstance(capture, dict) else None,
                                "y": capture.get("pixel_ratio_y") if isinstance(capture, dict) else None,
                            },
                            "mapping_kind": capture.get("mapping", {}).get("kind")
                            if isinstance(capture, dict) and isinstance(capture.get("mapping"), dict)
                            else None,
                        }
                    )
                except WispHandError as exc:
                    results.append({"monitor": name, "ok": False, "error": exc.to_payload()})
                finally:
                    runtime.close_session(session_id=opened["session_id"])

            report["checks"]["capture_check"] = {"ok": True, "results": results}

        if args.active_probe:
            report["progress"] = {"phase": "active_probe", "updated_at": time.time()}
            try:
                raw_topology = runtime._hyprland.get_topology()
                probe = runtime._coordinates.run_active_pointer_probe(
                    raw_topology,
                    hyprland=runtime._hyprland,
                    input_backend=runtime._input_backend,
                )
            except WispHandError as exc:
                report["checks"]["active_probe"] = {"ok": False, "error": exc.to_payload()}
            else:
                report["checks"]["active_probe"] = {
                    "ok": True,
                    "backend": probe.coordinate_map.backend,
                    "confidence": probe.coordinate_map.confidence,
                    "topology_fingerprint": probe.coordinate_map.topology_fingerprint,
                    "expected": probe.expected,
                    "observed": probe.observed,
                    "error_px": probe.error_px,
                }

        report["progress"] = {"phase": "done", "updated_at": time.time()}
        write_out()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
