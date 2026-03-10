from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from PIL import Image

from wisp_hand.capabilities import DependencyProbe
from wisp_hand.capture import CaptureArtifactStore, CaptureEngine
from wisp_hand.command import CommandResult
from wisp_hand.config import load_runtime_config
from wisp_hand.hyprland import HyprlandAdapter, desktop_bounds
from wisp_hand.runtime import WispHandRuntime
from wisp_hand.server import WispHandServer

TOPOLOGY_FIXTURE = {
    "monitors": [
        {"id": 0, "name": "HDMI-A-1", "x": 0, "y": 0, "width": 1920, "height": 1080},
        {"id": 1, "name": "DP-1", "x": 1920, "y": 0, "width": 1280, "height": 1080},
    ],
    "workspaces": [
        {"id": 1, "name": "1", "monitor": "HDMI-A-1"},
        {"id": 2, "name": "2", "monitor": "DP-1"},
    ],
    "activeworkspace": {"id": 1, "name": "1", "monitor": "HDMI-A-1"},
    "activewindow": {
        "address": "0xabc",
        "class": "Alacritty",
        "title": "shell",
        "at": [50, 60],
        "size": [900, 700],
        "workspace": {"id": 1, "name": "1"},
    },
    "clients": [
        {
            "address": "0xabc",
            "class": "Alacritty",
            "title": "shell",
            "at": [50, 60],
            "size": [900, 700],
            "workspace": {"id": 1, "name": "1"},
        },
        {
            "address": "0xdef",
            "class": "Firefox",
            "title": "docs",
            "at": [2000, 100],
            "size": [1000, 800],
            "workspace": {"id": 2, "name": "2"},
        },
    ],
    "cursorpos": {"x": 140, "y": 250},
}


class FakeObserveRunner:
    def __init__(self, *, fail_grim: bool = False) -> None:
        self.calls: list[list[str]] = []
        self.fail_grim = fail_grim

    def __call__(self, args: list[str]) -> CommandResult:
        self.calls.append(args)

        if args[0] == "hyprctl":
            return CommandResult(
                args=args,
                stdout=json.dumps(TOPOLOGY_FIXTURE[args[2]]),
                stderr="",
                returncode=0,
            )

        if args[0] == "grim":
            if self.fail_grim:
                return CommandResult(args=args, stdout="", stderr="grim failed", returncode=1)

            geometry = None
            if "-g" in args:
                geometry = self._parse_geometry(args[args.index("-g") + 1])
            else:
                geometry = desktop_bounds({"monitors": TOPOLOGY_FIXTURE["monitors"]})

            output_path = Path(args[-1])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (geometry["width"], geometry["height"]), color=(12, 34, 56)).save(
                output_path,
                format="PNG",
            )
            return CommandResult(args=args, stdout="", stderr="", returncode=0)

        raise AssertionError(f"Unexpected command: {args}")

    @staticmethod
    def _parse_geometry(value: str) -> dict[str, int]:
        origin, size = value.split(" ")
        x, y = origin.split(",")
        width, height = size.split("x")
        return {
            "x": int(x),
            "y": int(y),
            "width": int(width),
            "height": int(height),
        }


def build_runtime(
    tmp_path: Path,
    runner: FakeObserveRunner,
    *,
    env: dict[str, str] | None = None,
    binary_resolver=None,
) -> WispHandRuntime:
    config = load_runtime_config(
        Path(
            tmp_path / "config.toml"
        )
    )
    if env is None:
        env = {"HYPRLAND_INSTANCE_SIGNATURE": "fixture"}
    resolver = binary_resolver or (lambda name: f"/usr/bin/{name}")
    return WispHandRuntime(
        config=config,
        dependency_probe=DependencyProbe(
            required_binaries=["hyprctl", "grim", "slurp"],
            optional_binaries=["wtype"],
            binary_resolver=resolver,
            env=env,
        ),
        hyprland_adapter=HyprlandAdapter(runner=runner, env=env),
        capture_engine=CaptureEngine(
            artifact_store=CaptureArtifactStore(base_dir=config.paths.capture_dir),
            runner=runner,
            binary_resolver=resolver,
        ),
    )


def write_config(path: Path) -> None:
    path.write_text(
        """
[server]
transport = "stdio"

[paths]
state_dir = "./state"
audit_file = "./state/audit.jsonl"
runtime_log_file = "./state/runtime.jsonl"
capture_dir = "./state/captures"
""".strip(),
        encoding="utf-8",
    )


def runtime_with_config(tmp_path: Path, runner: FakeObserveRunner, **kwargs: Any) -> WispHandRuntime:
    write_config(tmp_path / "config.toml")
    return build_runtime(tmp_path, runner, **kwargs)


def test_topology_and_cursor_relative_coordinates(tmp_path: Path) -> None:
    runner = FakeObserveRunner()
    runtime = runtime_with_config(tmp_path, runner)
    server = WispHandServer(runtime)
    opened = runtime.open_session(
        scope_type="region",
        scope_target={"x": 100, "y": 200, "width": 300, "height": 300},
        armed=None,
        dry_run=None,
        ttl_seconds=30,
    )

    async def run_test() -> None:
        topology = await server.mcp.call_tool("wisp_hand.desktop.get_topology", {})
        assert topology.isError is False
        assert len(topology.structuredContent["monitors"]) == 2

        cursor = await server.mcp.call_tool(
            "wisp_hand.cursor.get_position",
            {"session_id": opened["session_id"]},
        )
        assert cursor.isError is False
        assert cursor.structuredContent == {
            "x": 140,
            "y": 250,
            "scope_x": 40,
            "scope_y": 50,
        }

    asyncio.run(run_test())


def test_topology_rejects_without_hyprland_environment(tmp_path: Path) -> None:
    runner = FakeObserveRunner()
    runtime = runtime_with_config(tmp_path, runner, env={})
    server = WispHandServer(runtime)

    async def run_test() -> None:
        result = await server.mcp.call_tool("wisp_hand.desktop.get_topology", {})
        assert result.isError is True
        assert result.structuredContent["code"] == "unsupported_environment"

    asyncio.run(run_test())


def test_capture_scope_creates_artifact_and_metadata(tmp_path: Path) -> None:
    runner = FakeObserveRunner()
    runtime = runtime_with_config(tmp_path, runner)
    server = WispHandServer(runtime)
    opened = runtime.open_session(
        scope_type="region",
        scope_target={"x": 10, "y": 20, "width": 100, "height": 80},
        armed=None,
        dry_run=None,
        ttl_seconds=30,
    )

    async def run_test() -> None:
        result = await server.mcp.call_tool(
            "wisp_hand.capture.screen",
            {
                "session_id": opened["session_id"],
                "target": "scope",
                "inline": True,
                "downscale": 0.5,
            },
        )
        assert result.isError is False
        payload = result.structuredContent
        assert payload["width"] == 50
        assert payload["height"] == 40
        assert payload["source_bounds"] == {"x": 10, "y": 20, "width": 100, "height": 80}
        assert payload["inline_base64"]

        image_path = Path(payload["path"])
        assert image_path.exists()

        metadata = CaptureArtifactStore(base_dir=image_path.parent).load_metadata(payload["capture_id"])
        assert metadata["capture_id"] == payload["capture_id"]
        assert metadata["scope"]["type"] == "region"
        assert metadata["source_bounds"]["width"] == 100

    asyncio.run(run_test())


def test_capture_supports_desktop_monitor_and_window_targets(tmp_path: Path) -> None:
    runner = FakeObserveRunner()
    runtime = runtime_with_config(tmp_path, runner)

    desktop_session = runtime.open_session(
        scope_type="desktop",
        scope_target=None,
        armed=None,
        dry_run=None,
        ttl_seconds=30,
    )
    monitor_session = runtime.open_session(
        scope_type="monitor",
        scope_target="DP-1",
        armed=None,
        dry_run=None,
        ttl_seconds=30,
    )
    window_session = runtime.open_session(
        scope_type="window",
        scope_target="0xdef",
        armed=None,
        dry_run=None,
        ttl_seconds=30,
    )

    desktop_capture = runtime.capture_screen(session_id=desktop_session["session_id"], target="desktop")
    monitor_capture = runtime.capture_screen(session_id=monitor_session["session_id"], target="monitor")
    window_capture = runtime.capture_screen(session_id=window_session["session_id"], target="window")

    assert desktop_capture["width"] == 3200
    assert desktop_capture["height"] == 1080
    assert monitor_capture["width"] == 1280
    assert monitor_capture["height"] == 1080
    assert window_capture["width"] == 1000
    assert window_capture["height"] == 800


def test_capture_dependency_missing_is_structured_error(tmp_path: Path) -> None:
    runner = FakeObserveRunner()
    runtime = runtime_with_config(
        tmp_path,
        runner,
        binary_resolver=lambda name: None if name == "grim" else f"/usr/bin/{name}",
    )
    server = WispHandServer(runtime)
    opened = runtime.open_session(
        scope_type="region",
        scope_target={"x": 0, "y": 0, "width": 10, "height": 10},
        armed=None,
        dry_run=None,
        ttl_seconds=30,
    )

    async def run_test() -> None:
        result = await server.mcp.call_tool(
            "wisp_hand.capture.screen",
            {"session_id": opened["session_id"], "target": "scope"},
        )
        assert result.isError is True
        assert result.structuredContent["code"] == "dependency_missing"

    asyncio.run(run_test())
