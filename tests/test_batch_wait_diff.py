from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from wisp_hand.capture import CaptureArtifactStore, CaptureEngine
from wisp_hand.command import CommandResult
from wisp_hand.config import load_runtime_config
from wisp_hand.errors import WispHandError
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


class FakeBatchRunner:
    def __init__(self, *, capture_colors: list[tuple[int, int, int]] | None = None) -> None:
        self.calls: list[list[str]] = []
        self._capture_colors = capture_colors or [(12, 34, 56)]
        self._capture_index = 0

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
            geometry = (
                self._parse_geometry(args[args.index("-g") + 1])
                if "-g" in args
                else desktop_bounds({"monitors": TOPOLOGY_FIXTURE["monitors"]})
            )
            color = self._capture_colors[min(self._capture_index, len(self._capture_colors) - 1)]
            self._capture_index += 1
            output_path = Path(args[-1])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (geometry["width"], geometry["height"]), color=color).save(
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


class FakeInputBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def move_pointer(self, *, x: int, y: int, desktop_bounds: dict[str, int]) -> None:
        self.calls.append(("move", {"x": x, "y": y, "desktop_bounds": desktop_bounds}))

    def click_pointer(
        self,
        *,
        x: int,
        y: int,
        button: str,
        desktop_bounds: dict[str, int],
    ) -> None:
        self.calls.append(
            ("click", {"x": x, "y": y, "button": button, "desktop_bounds": desktop_bounds})
        )

    def drag_pointer(
        self,
        *,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        button: str,
        desktop_bounds: dict[str, int],
    ) -> None:
        self.calls.append(
            (
                "drag",
                {
                    "start_x": start_x,
                    "start_y": start_y,
                    "end_x": end_x,
                    "end_y": end_y,
                    "button": button,
                    "desktop_bounds": desktop_bounds,
                },
            )
        )

    def scroll_pointer(
        self,
        *,
        x: int,
        y: int,
        delta_x: int,
        delta_y: int,
        desktop_bounds: dict[str, int],
    ) -> None:
        self.calls.append(
            (
                "scroll",
                {
                    "x": x,
                    "y": y,
                    "delta_x": delta_x,
                    "delta_y": delta_y,
                    "desktop_bounds": desktop_bounds,
                },
            )
        )

    def type_text(self, *, text: str) -> None:
        self.calls.append(("type", {"text": text}))

    def press_keys(self, *, keys: list[str]) -> None:
        self.calls.append(("press", {"keys": list(keys)}))


class FakeSleeper:
    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


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

[session]
default_ttl_seconds = 30
max_ttl_seconds = 120
""".strip(),
        encoding="utf-8",
    )


def build_runtime(
    tmp_path: Path,
    *,
    runner: FakeBatchRunner | None = None,
    input_backend: FakeInputBackend | None = None,
    sleeper: FakeSleeper | None = None,
) -> tuple[WispHandRuntime, FakeInputBackend, FakeSleeper]:
    write_config(tmp_path / "config.toml")
    fake_runner = runner or FakeBatchRunner()
    backend = input_backend or FakeInputBackend()
    fake_sleeper = sleeper or FakeSleeper()
    config = load_runtime_config(tmp_path / "config.toml")
    resolver = lambda name: f"/usr/bin/{name}"

    runtime = WispHandRuntime(
        config=config,
        hyprland_adapter=HyprlandAdapter(
            runner=fake_runner,
            env={"HYPRLAND_INSTANCE_SIGNATURE": "fixture"},
        ),
        capture_engine=CaptureEngine(
            artifact_store=CaptureArtifactStore(base_dir=config.paths.capture_dir),
            runner=fake_runner,
            binary_resolver=resolver,
        ),
        input_backend=backend,
        sleep_provider=fake_sleeper,
    )
    return runtime, backend, fake_sleeper


def write_capture(
    capture_dir: Path,
    *,
    capture_id: str,
    pixels: list[tuple[int, int, int]],
    size: tuple[int, int],
) -> None:
    image_path = capture_dir / f"{capture_id}.png"
    metadata_path = capture_dir / f"{capture_id}.json"
    image = Image.new("RGB", size)
    image.putdata(pixels)
    image.save(image_path, format="PNG")
    CaptureArtifactStore(base_dir=capture_dir).write_metadata(
        metadata_path=metadata_path,
        payload={
            "capture_id": capture_id,
            "scope": {
                "type": "region",
                "target": {"x": 0, "y": 0, "width": size[0], "height": size[1]},
                "coordinate_space": {"origin": "scope", "units": "px", "relative_to": "region"},
                "constraints": {"input_relative": True},
            },
            "target": "scope",
            "width": size[0],
            "height": size[1],
            "mime_type": "image/png",
            "created_at": "2026-03-09T00:00:00+00:00",
            "source_bounds": {"x": 0, "y": 0, "width": size[0], "height": size[1]},
            "downscale": None,
        },
    )


def test_batch_runs_steps_in_order_and_audit_links_steps(tmp_path: Path) -> None:
    runtime, backend, sleeper = build_runtime(tmp_path)
    session = runtime.open_session(
        scope_type="region",
        scope_target={"x": 100, "y": 200, "width": 300, "height": 300},
        armed=True,
        dry_run=None,
        ttl_seconds=30,
    )

    result = runtime.batch_run(
        session_id=session["session_id"],
        stop_on_error=True,
        steps=[
            {"type": "move", "x": 5, "y": 6},
            {"type": "wait", "duration_ms": 250},
            {"type": "type", "text": "hello"},
            {"type": "capture", "target": "scope"},
        ],
    )

    assert result["session_id"] == session["session_id"]
    assert result["return_mode"] == "summary"
    assert [step["type"] for step in result["steps"]] == ["move", "wait", "type", "capture"]
    assert [step["status"] for step in result["steps"]] == ["ok", "ok", "ok", "ok"]
    assert backend.calls == [
        ("move", {"x": 105, "y": 206, "desktop_bounds": {"x": 0, "y": 0, "width": 3200, "height": 1080}}),
        ("type", {"text": "hello"}),
    ]
    assert sleeper.calls == [0.25]

    assert "output" not in result["steps"][0]
    assert "output" not in result["steps"][1]
    assert "output" not in result["steps"][2]
    capture_output = result["steps"][3]["output"]
    assert isinstance(capture_output, dict)
    assert "target" not in capture_output
    assert isinstance(capture_output.get("capture_id"), str) and capture_output["capture_id"]

    audit_path = runtime.config.paths.audit_file
    assert audit_path is not None and audit_path.exists()
    audit_entries = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    child_entries = [entry for entry in audit_entries if entry.get("parent_tool_name") == "wisp_hand.batch.run"]
    assert {entry["tool_name"] for entry in child_entries} == {
        "wisp_hand.pointer.move",
        "wisp_hand.wait",
        "wisp_hand.keyboard.type",
        "wisp_hand.capture.screen",
    }
    assert {entry["batch_id"] for entry in child_entries} == {result["batch_id"]}
    assert {entry["step_index"] for entry in child_entries} == {0, 1, 2, 3}


def test_batch_return_mode_full_keeps_step_outputs(tmp_path: Path) -> None:
    runtime, _, _ = build_runtime(tmp_path)
    session = runtime.open_session(
        scope_type="region",
        scope_target={"x": 0, "y": 0, "width": 10, "height": 10},
        armed=True,
        dry_run=None,
        ttl_seconds=30,
    )

    result = runtime.batch_run(
        session_id=session["session_id"],
        stop_on_error=True,
        return_mode="full",
        steps=[{"type": "capture", "target": "scope"}],
    )
    assert result["return_mode"] == "full"
    assert result["steps"][0]["status"] == "ok"
    output = result["steps"][0]["output"]
    assert isinstance(output, dict)
    assert output["target"] == "scope"
    assert isinstance(output.get("capture_id"), str) and output["capture_id"]


def test_batch_fail_fast_continue_and_invalid_step_type(tmp_path: Path) -> None:
    runtime, backend, _ = build_runtime(tmp_path)
    session = runtime.open_session(
        scope_type="region",
        scope_target={"x": 100, "y": 200, "width": 50, "height": 50},
        armed=True,
        dry_run=None,
        ttl_seconds=30,
    )

    fail_fast = runtime.batch_run(
        session_id=session["session_id"],
        stop_on_error=True,
        steps=[
            {"type": "move", "x": 1, "y": 1},
            {"type": "click", "x": 60, "y": 0},
            {"type": "type", "text": "after"},
        ],
    )
    assert [step["status"] for step in fail_fast["steps"]] == ["ok", "error", "skipped"]
    assert backend.calls == [
        ("move", {"x": 101, "y": 201, "desktop_bounds": {"x": 0, "y": 0, "width": 3200, "height": 1080}}),
    ]

    backend.calls.clear()
    continue_run = runtime.batch_run(
        session_id=session["session_id"],
        stop_on_error=False,
        steps=[
            {"type": "move", "x": 1, "y": 1},
            {"type": "click", "x": 60, "y": 0},
            {"type": "type", "text": "after"},
        ],
    )
    assert [step["status"] for step in continue_run["steps"]] == ["ok", "error", "ok"]
    assert backend.calls == [
        ("move", {"x": 101, "y": 201, "desktop_bounds": {"x": 0, "y": 0, "width": 3200, "height": 1080}}),
        ("type", {"text": "after"}),
    ]

    server = WispHandServer(runtime)

    async def run_invalid() -> None:
        invalid = await server.mcp.call_tool(
            "wisp_hand.batch.run",
            {
                "session_id": session["session_id"],
                "steps": [{"type": "unknown"}],
            },
        )
        assert invalid.isError is True
        assert invalid.structuredContent["code"] == "invalid_parameters"

    asyncio.run(run_invalid())


def test_wait_and_capture_diff_cover_ratio_and_missing_capture(tmp_path: Path) -> None:
    runtime, _, sleeper = build_runtime(tmp_path)
    session = runtime.open_session(
        scope_type="region",
        scope_target={"x": 0, "y": 0, "width": 10, "height": 10},
        armed=True,
        dry_run=None,
        ttl_seconds=30,
    )

    waited = runtime.wait(session_id=session["session_id"], duration_ms=125)
    assert waited["session_id"] == session["session_id"]
    assert waited["duration_ms"] == 125
    assert sleeper.calls == [0.125]

    capture_dir = runtime.config.paths.capture_dir
    write_capture(
        capture_dir,
        capture_id="left",
        size=(2, 2),
        pixels=[(255, 0, 0), (255, 0, 0), (255, 0, 0), (255, 0, 0)],
    )
    write_capture(
        capture_dir,
        capture_id="right",
        size=(2, 2),
        pixels=[(255, 0, 0), (255, 0, 0), (255, 0, 0), (0, 0, 255)],
    )

    diff = runtime.capture_diff(left_capture_id="left", right_capture_id="right")
    assert diff["changed"] is True
    assert diff["changed_pixels"] == 1
    assert diff["total_pixels"] == 4
    assert diff["change_ratio"] == 0.25
    assert "1/4 pixels changed (0.250000)" in diff["summary"]

    write_capture(
        capture_dir,
        capture_id="same",
        size=(2, 2),
        pixels=[(1, 2, 3), (1, 2, 3), (1, 2, 3), (1, 2, 3)],
    )
    no_change = runtime.capture_diff(left_capture_id="same", right_capture_id="same")
    assert no_change["changed"] is False
    assert no_change["change_ratio"] == 0.0

    with pytest.raises(WispHandError) as missing_exc:
        runtime.capture_diff(left_capture_id="missing", right_capture_id="same")
    assert missing_exc.value.code == "capability_unavailable"
