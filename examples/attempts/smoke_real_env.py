from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
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


def _write_runtime_config(
    *,
    config_path: Path,
    state_dir: Path,
    vision: dict[str, Any] | None,
    logging: dict[str, Any] | None,
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
        f'level = "{(logging or {}).get("level", "INFO")}"',
        f'allow_sensitive = {str(bool((logging or {}).get("allow_sensitive", False))).lower()}',
        "",
        "[logging.console]",
        f'enabled = {str(bool((logging or {}).get("console_enabled", False))).lower()}',
        f'format = "{(logging or {}).get("console_format", "plain")}"',
        "",
        "[logging.file]",
        f'enabled = {str(bool((logging or {}).get("file_enabled", True))).lower()}',
        f'format = "{(logging or {}).get("file_format", "json")}"',
        "",
        "[session]",
        "default_ttl_seconds = 60",
        "max_ttl_seconds = 300",
        "",
        "[safety]",
        "default_armed = false",
        "default_dry_run = false",
        "dangerous_shortcuts = [\"ctrl+alt+delete\"]",
        "",
    ]

    if vision is not None:
        lines.extend(
            [
                "[vision]",
                f'mode = "{vision["mode"]}"',
                f'model = "{vision["model"]}"',
                f'base_url = "{vision["base_url"]}"',
                f"timeout_seconds = {vision['timeout_seconds']}",
                f"max_image_edge = {vision['max_image_edge']}",
                f"max_tokens = {vision['max_tokens']}",
                f"max_concurrency = {vision['max_concurrency']}",
                "",
            ]
        )

    config_path.write_text("\n".join(lines), encoding="utf-8")


def _load_monitors() -> list[dict[str, Any]]:
    import subprocess

    try:
        result = subprocess.run(
            ["hyprctl", "-j", "monitors"],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("hyprctl is missing") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"hyprctl failed: {exc.stderr}") from exc

    payload = json.loads(result.stdout)
    if not isinstance(payload, list):
        raise RuntimeError("hyprctl monitors payload is not a list")
    return payload


def _pick_region(
    *,
    monitors: list[dict[str, Any]],
    prefer_scaled: bool,
    size: int,
) -> Region:
    selected: dict[str, Any] | None = None
    for monitor in monitors:
        scale = monitor.get("scale")
        if isinstance(scale, (int, float)) and ((scale != 1.0) == prefer_scaled):
            selected = monitor
            break

    if selected is None:
        selected = monitors[0] if monitors else None

    if selected is None:
        raise RuntimeError("no monitors found")

    x = int(selected.get("x", 0))
    y = int(selected.get("y", 0))
    return Region(x=x, y=y, width=size, height=size)


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


@contextlib.contextmanager
def _timeout(seconds: float, *, label: str) -> None:
    if seconds <= 0:
        yield
        return

    def handler(signum, frame) -> None:  # noqa: ARG001
        raise TimeoutError(f"{label} timed out after {seconds:.1f}s")

    previous = signal.signal(signal.SIGALRM, handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _call_and_capture_error(fn, *args, timeout_seconds: float | None = None, label: str = "", **kwargs):
    try:
        if timeout_seconds is None:
            return {"ok": True, "value": fn(*args, **kwargs)}
        with _timeout(timeout_seconds, label=label or getattr(fn, "__name__", "call")):
            return {"ok": True, "value": fn(*args, **kwargs)}
    except WispHandError as exc:
        return {"ok": False, "error": exc.to_payload()}
    except TimeoutError as exc:
        return {"ok": False, "error": {"code": "timeout", "message": str(exc), "details": {}}}
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": {"code": type(exc).__name__, "message": str(exc), "details": {}},
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="smoke_real_env")
    parser.add_argument(
        "--out",
        type=Path,
        help="Write JSON report to this path (defaults to stdout).",
    )
    parser.add_argument(
        "--region-size",
        type=int,
        default=120,
        help="Default square region size for capture scaling checks.",
    )
    parser.add_argument(
        "--scaled-region",
        type=_region_from_string,
        help="Override scaled-region as x,y,width,height in Hyprland layout coordinates.",
    )
    parser.add_argument(
        "--unscaled-region",
        type=_region_from_string,
        help="Override scale-1 region as x,y,width,height in Hyprland layout coordinates.",
    )
    parser.add_argument(
        "--input",
        choices=["none", "dry-run", "real"],
        default="none",
        help="Run input checks: dry-run is side-effect free; real will dispatch pointer+keyboard.",
    )
    parser.add_argument(
        "--step-timeout-seconds",
        type=float,
        default=5.0,
        help="Per-step timeout for potentially blocking operations (e.g. real input dispatch).",
    )
    parser.add_argument(
        "--input-region",
        type=_region_from_string,
        help="Region used for input checks (required for --input real).",
    )
    parser.add_argument(
        "--confirm-real-input",
        action="store_true",
        help="Required to run --input real.",
    )
    parser.add_argument(
        "--vision",
        action="store_true",
        help="Run vision describe on a capture (requires Ollama).",
    )
    parser.add_argument(
        "--vision-model",
        default="qwen3.5:0.8b",
        help="Ollama model name used for vision requests.",
    )
    parser.add_argument(
        "--vision-base-url",
        default="http://127.0.0.1:11434",
        help="Ollama base URL.",
    )
    parser.add_argument(
        "--log-console",
        action="store_true",
        help="Enable console logging (always stderr).",
    )
    parser.add_argument(
        "--log-console-format",
        choices=["json", "rich", "plain"],
        default="plain",
        help="Console log format.",
    )
    parser.add_argument(
        "--log-file-format",
        choices=["json", "plain"],
        default="json",
        help="Runtime log file format.",
    )
    parser.add_argument(
        "--log-allow-sensitive",
        action="store_true",
        help="Allow sensitive fields in logs/audit (unsafe).",
    )
    args = parser.parse_args(argv)

    def write_out() -> None:
        if not args.out:
            return
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report: dict[str, Any] = {
        "progress": {"phase": "init", "step": None, "updated_at": time.time()},
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
            "ollama": _binary_path("ollama"),
        },
        "monitors": [],
        "checks": {},
        "logs": {},
    }
    write_out()

    try:
        monitors = _load_monitors()
    except Exception as exc:  # noqa: BLE001
        report["checks"]["hyprctl"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        monitors = []
    else:
        report["checks"]["hyprctl"] = {"ok": True}
        for monitor in monitors:
            scale = monitor.get("scale")
            width = monitor.get("width")
            height = monitor.get("height")
            logical_width = None
            logical_height = None
            if isinstance(scale, (int, float)) and scale > 0 and isinstance(width, int) and isinstance(height, int):
                logical_width = round(width / scale)
                logical_height = round(height / scale)
            report["monitors"].append(
                {
                    "name": monitor.get("name"),
                    "x": monitor.get("x"),
                    "y": monitor.get("y"),
                    "width": width,
                    "height": height,
                    "scale": scale,
                    "focused": monitor.get("focused"),
                    "logical_width": logical_width,
                    "logical_height": logical_height,
                }
            )
        report["progress"] = {"phase": "monitors", "step": None, "updated_at": time.time()}
        write_out()

    vision_config: dict[str, Any] | None = None
    if args.vision:
        vision_config = {
            "mode": "assist",
            "model": str(args.vision_model),
            "base_url": str(args.vision_base_url),
            "timeout_seconds": 8.0,
            "max_image_edge": 512,
            "max_tokens": 128,
            "max_concurrency": 1,
        }

    with tempfile.TemporaryDirectory(prefix="wisp-hand-smoke-") as temp_root:
        root = Path(temp_root)
        state_dir = root / "state"
        config_path = root / "config.toml"
        logging_config = {
            "level": "INFO",
            "allow_sensitive": bool(args.log_allow_sensitive),
            "console_enabled": bool(args.log_console),
            "console_format": str(args.log_console_format),
            "file_enabled": True,
            "file_format": str(args.log_file_format),
        }
        _write_runtime_config(
            config_path=config_path,
            state_dir=state_dir,
            vision=vision_config,
            logging=logging_config,
        )
        runtime = WispHandRuntime(config=load_runtime_config(config_path))
        report["logs"] = {
            "config_path": str(config_path),
            "audit_file": str(state_dir / "audit.jsonl"),
            "runtime_log_file": str(state_dir / "runtime.jsonl"),
        }

        report["progress"] = {"phase": "capabilities", "step": None, "updated_at": time.time()}
        write_out()
        report["checks"]["capabilities"] = _call_and_capture_error(
            runtime.capabilities,
            timeout_seconds=args.step_timeout_seconds,
            label="hand.capabilities",
        )
        write_out()

        scaled_region = args.scaled_region or _pick_region(
            monitors=monitors,
            prefer_scaled=True,
            size=args.region_size,
        )
        unscaled_region = args.unscaled_region or _pick_region(
            monitors=monitors,
            prefer_scaled=False,
            size=args.region_size,
        )

        report["checks"]["capture_scaling"] = []
        for name, region in [("scaled", scaled_region), ("unscaled", unscaled_region)]:
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
                report["progress"] = {"phase": "capture_scaling", "step": name, "updated_at": time.time()}
                write_out()
                captured = runtime.capture_screen(session_id=opened["session_id"], target="scope", inline=False)
                source_bounds = captured.get("source_bounds") or {}
                source_w = source_bounds.get("width")
                source_h = source_bounds.get("height")
                cap_w = captured.get("width")
                cap_h = captured.get("height")
                ratio_w = (cap_w / source_w) if isinstance(cap_w, int) and isinstance(source_w, int) and source_w else None
                ratio_h = (cap_h / source_h) if isinstance(cap_h, int) and isinstance(source_h, int) and source_h else None
                report["checks"]["capture_scaling"].append(
                    {
                        "name": name,
                        "scope_target": {
                            "x": region.x,
                            "y": region.y,
                            "width": region.width,
                            "height": region.height,
                        },
                        "source_bounds": source_bounds,
                        "captured_size": {"width": cap_w, "height": cap_h},
                        "ratio": {"width": ratio_w, "height": ratio_h},
                        "capture_id": captured.get("capture_id"),
                        "path": captured.get("path"),
                    }
                )
            except WispHandError as exc:
                report["checks"]["capture_scaling"].append({"name": name, "ok": False, "error": exc.to_payload()})
            finally:
                runtime.close_session(session_id=opened["session_id"])
                write_out()

        report["checks"]["safety"] = {}

        # Unarmed pointer should be rejected.
        unarmed = runtime.open_session(
            scope_type="region",
            scope_target={"x": scaled_region.x, "y": scaled_region.y, "width": 100, "height": 100},
            armed=False,
            dry_run=False,
            ttl_seconds=60,
        )
        try:
            report["checks"]["safety"]["unarmed_pointer_move"] = _call_and_capture_error(
                runtime.pointer_move,
                session_id=unarmed["session_id"],
                x=10,
                y=10,
                timeout_seconds=args.step_timeout_seconds,
                label="hand.pointer.move (unarmed)",
            )
        finally:
            runtime.close_session(session_id=unarmed["session_id"])
            report["progress"] = {"phase": "safety", "step": "unarmed_pointer_move", "updated_at": time.time()}
            write_out()

        dry = runtime.open_session(
            scope_type="region",
            scope_target={"x": scaled_region.x, "y": scaled_region.y, "width": 200, "height": 200},
            armed=True,
            dry_run=True,
            ttl_seconds=60,
        )
        try:
            report["checks"]["safety"]["dry_run_pointer_click"] = _call_and_capture_error(
                runtime.pointer_click,
                session_id=dry["session_id"],
                x=10,
                y=10,
                button="left",
                timeout_seconds=args.step_timeout_seconds,
                label="hand.pointer.click (dry-run)",
            )
            report["checks"]["safety"]["dry_run_keyboard_press"] = _call_and_capture_error(
                runtime.keyboard_press,
                session_id=dry["session_id"],
                keys=["ctrl", "a"],
                timeout_seconds=args.step_timeout_seconds,
                label="hand.keyboard.press (dry-run)",
            )
            report["checks"]["safety"]["dry_run_keyboard_type"] = _call_and_capture_error(
                runtime.keyboard_type,
                session_id=dry["session_id"],
                text="wisp-hand-dry-run",
                timeout_seconds=args.step_timeout_seconds,
                label="hand.keyboard.type (dry-run)",
            )
        finally:
            runtime.close_session(session_id=dry["session_id"])
            report["progress"] = {"phase": "safety", "step": "dry_run", "updated_at": time.time()}
            write_out()

        armed = runtime.open_session(
            scope_type="region",
            scope_target={"x": scaled_region.x, "y": scaled_region.y, "width": 200, "height": 200},
            armed=True,
            dry_run=False,
            ttl_seconds=60,
        )
        try:
            report["checks"]["safety"]["dangerous_shortcut"] = _call_and_capture_error(
                runtime.keyboard_press,
                session_id=armed["session_id"],
                keys=["ctrl", "alt", "delete"],
                timeout_seconds=args.step_timeout_seconds,
                label="hand.keyboard.press (dangerous shortcut)",
            )
        finally:
            runtime.close_session(session_id=armed["session_id"])
            report["progress"] = {"phase": "safety", "step": "dangerous_shortcut", "updated_at": time.time()}
            write_out()

        report["checks"]["input"] = {"mode": args.input, "results": {}}
        if args.input == "dry-run":
            input_region = args.input_region or scaled_region
            input_session = runtime.open_session(
                scope_type="region",
                scope_target={
                    "x": input_region.x,
                    "y": input_region.y,
                    "width": input_region.width,
                    "height": input_region.height,
                },
                armed=True,
                dry_run=True,
                ttl_seconds=60,
            )
            try:
                report["checks"]["input"]["results"]["pointer_move"] = _call_and_capture_error(
                    runtime.pointer_move,
                    session_id=input_session["session_id"],
                    x=20,
                    y=20,
                    timeout_seconds=args.step_timeout_seconds,
                    label="hand.pointer.move (input dry-run)",
                )
                report["checks"]["input"]["results"]["pointer_click"] = _call_and_capture_error(
                    runtime.pointer_click,
                    session_id=input_session["session_id"],
                    x=20,
                    y=20,
                    button="left",
                    timeout_seconds=args.step_timeout_seconds,
                    label="hand.pointer.click (input dry-run)",
                )
                report["checks"]["input"]["results"]["pointer_scroll"] = _call_and_capture_error(
                    runtime.pointer_scroll,
                    session_id=input_session["session_id"],
                    x=20,
                    y=20,
                    delta_y=-120,
                    timeout_seconds=args.step_timeout_seconds,
                    label="hand.pointer.scroll (input dry-run)",
                )
                report["checks"]["input"]["results"]["keyboard_type"] = _call_and_capture_error(
                    runtime.keyboard_type,
                    session_id=input_session["session_id"],
                    text="wisp-hand-dry-run-input",
                    timeout_seconds=args.step_timeout_seconds,
                    label="hand.keyboard.type (input dry-run)",
                )
            finally:
                runtime.close_session(session_id=input_session["session_id"])
                report["progress"] = {"phase": "input", "step": "dry-run", "updated_at": time.time()}
                write_out()

        if args.input == "real":
            if not args.confirm_real_input:
                report["checks"]["input"]["results"]["blocked"] = {
                    "ok": False,
                    "error": "missing --confirm-real-input",
                }
            elif args.input_region is None:
                report["checks"]["input"]["results"]["blocked"] = {
                    "ok": False,
                    "error": "missing --input-region x,y,width,height",
                }
            else:
                region = args.input_region
                input_session = runtime.open_session(
                    scope_type="region",
                    scope_target={"x": region.x, "y": region.y, "width": region.width, "height": region.height},
                    armed=True,
                    dry_run=False,
                    ttl_seconds=30,
                )
                try:
                    report["progress"] = {"phase": "input", "step": "real.pointer_move", "updated_at": time.time()}
                    write_out()
                    report["checks"]["input"]["results"]["pointer_move"] = _call_and_capture_error(
                        runtime.pointer_move,
                        session_id=input_session["session_id"],
                        x=40,
                        y=40,
                        timeout_seconds=args.step_timeout_seconds,
                        label="hand.pointer.move (real)",
                    )
                    report["progress"] = {"phase": "input", "step": "real.pointer_click", "updated_at": time.time()}
                    write_out()
                    report["checks"]["input"]["results"]["pointer_click"] = _call_and_capture_error(
                        runtime.pointer_click,
                        session_id=input_session["session_id"],
                        x=40,
                        y=40,
                        button="left",
                        timeout_seconds=args.step_timeout_seconds,
                        label="hand.pointer.click (real)",
                    )
                    report["progress"] = {"phase": "input", "step": "real.pointer_scroll", "updated_at": time.time()}
                    write_out()
                    report["checks"]["input"]["results"]["pointer_scroll"] = _call_and_capture_error(
                        runtime.pointer_scroll,
                        session_id=input_session["session_id"],
                        x=40,
                        y=40,
                        delta_y=-120,
                        timeout_seconds=args.step_timeout_seconds,
                        label="hand.pointer.scroll (real)",
                    )
                    report["progress"] = {"phase": "input", "step": "real.keyboard_type", "updated_at": time.time()}
                    write_out()
                    report["checks"]["input"]["results"]["keyboard_type"] = _call_and_capture_error(
                        runtime.keyboard_type,
                        session_id=input_session["session_id"],
                        text="wisp-hand-real-input",
                        timeout_seconds=args.step_timeout_seconds,
                        label="hand.keyboard.type (real)",
                    )
                finally:
                    runtime.close_session(session_id=input_session["session_id"])
                    report["progress"] = {"phase": "input", "step": "real.done", "updated_at": time.time()}
                    write_out()

        if args.vision:
            report["checks"]["vision"] = {"model": args.vision_model}
            opened = runtime.open_session(
                scope_type="region",
                scope_target={"x": scaled_region.x, "y": scaled_region.y, "width": 220, "height": 160},
                armed=False,
                dry_run=False,
                ttl_seconds=60,
            )
            try:
                report["progress"] = {"phase": "vision", "step": "capture", "updated_at": time.time()}
                write_out()
                cap = runtime.capture_screen(session_id=opened["session_id"], target="scope", inline=False)
                report["checks"]["vision"]["capture"] = {
                    "capture_id": cap.get("capture_id"),
                    "width": cap.get("width"),
                    "height": cap.get("height"),
                    "path": cap.get("path"),
                }
                report["progress"] = {"phase": "vision", "step": "describe", "updated_at": time.time()}
                write_out()
                report["checks"]["vision"]["describe"] = _call_and_capture_error(
                    runtime.vision_describe,
                    capture_id=str(cap.get("capture_id")),
                    prompt="Describe the screenshot briefly.",
                    timeout_seconds=max(0.0, args.step_timeout_seconds * 4),
                    label="hand.vision.describe",
                )
            finally:
                runtime.close_session(session_id=opened["session_id"])
                report["progress"] = {"phase": "vision", "step": "done", "updated_at": time.time()}
                write_out()

        report["progress"] = {"phase": "logging", "step": None, "updated_at": time.time()}
        write_out()
        try:
            import logging as py_logging
            import sys as py_sys

            root_logger = py_logging.getLogger()
            stdout_handlers = [
                handler
                for handler in root_logger.handlers
                if isinstance(handler, py_logging.StreamHandler)
                and getattr(handler, "stream", None) in {py_sys.stdout, py_sys.__stdout__}
            ]
            report["checks"]["logging"] = {
                "stdout_safe": not stdout_handlers,
                "runtime_log_file_format": args.log_file_format,
                "runtime_log_file_parseable": None,
                "runtime_log_file_has_required_fields": None,
                "runtime_log_file_lines": 0,
            }
        except Exception as exc:  # noqa: BLE001
            report["checks"]["logging"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

        runtime_log_path = state_dir / "runtime.jsonl"
        if args.log_file_format == "json" and runtime_log_path.exists():
            try:
                lines = runtime_log_path.read_text(encoding="utf-8").splitlines()
                parsed = [json.loads(line) for line in lines if line]
                required_ok = all(
                    isinstance(entry, dict)
                    and "timestamp" in entry
                    and "level" in entry
                    and "event" in entry
                    and "component" in entry
                    for entry in parsed
                )
                report["checks"]["logging"]["runtime_log_file_parseable"] = True
                report["checks"]["logging"]["runtime_log_file_has_required_fields"] = required_ok
                report["checks"]["logging"]["runtime_log_file_lines"] = len(parsed)
            except Exception as exc:  # noqa: BLE001
                report["checks"]["logging"]["runtime_log_file_parseable"] = False
                report["checks"]["logging"]["error"] = f"{type(exc).__name__}: {exc}"
        write_out()

        report["progress"] = {"phase": "done", "step": None, "updated_at": time.time()}
        write_out()
        if not args.out:
            print(json.dumps(report, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
