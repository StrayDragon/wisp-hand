from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from PIL import Image

from wisp_hand.capture import CaptureArtifactStore, CaptureEngine
from wisp_hand.infra.command import CommandResult
from wisp_hand.infra.config import load_runtime_config
from wisp_hand.coordinates.backends import resolve_hyprctl_infer
from wisp_hand.desktop.hyprland_adapter import HyprlandAdapter
from wisp_hand.app.runtime import WispHandRuntime
from wisp_hand.protocol.mcp_server import WispHandServer


def write_config(path: Path, *, coordinates_mode: str) -> None:
    path.write_text(
        f"""
[server]
transport = "stdio"

[paths]
state_dir = "./state"
audit_file = "./state/audit.jsonl"
runtime_log_file = "./state/runtime.jsonl"
capture_dir = "./state/captures"

[coordinates]
mode = "{coordinates_mode}"
cache_enabled = false
probe_region_size = 120
min_confidence = 0.75
""".strip(),
        encoding="utf-8",
    )


MIXED_SCALE_TOPOLOGY_FIXTURE: dict[str, Any] = {
    "monitors": [
        {
            "id": 0,
            "name": "eDP-1",
            "x": 0,
            "y": 0,
            # Hyprland reports these as framebuffer/physical pixels for fractional scaling.
            "width": 2560,
            "height": 1600,
            "scale": 1.25,
        },
        {
            "id": 1,
            "name": "HDMI-A-1",
            "x": 2048,
            "y": 0,
            "width": 1920,
            "height": 1080,
            "scale": 1.0,
        },
    ],
    "workspaces": [],
    "activeworkspace": {},
    "activewindow": {},
    "clients": [],
    "cursorpos": {"x": 10, "y": 10},
}


class FakeMixedScaleRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> CommandResult:
        self.calls.append(args)

        if args[:2] == ["hyprctl", "-j"]:
            key = args[2]
            return CommandResult(args=args, stdout=json.dumps(MIXED_SCALE_TOPOLOGY_FIXTURE[key]), stderr="", returncode=0)

        if args[0] == "grim":
            # grim geometry is in layout px, but output is in image px (framebuffer), so simulate scaling.
            if "-g" not in args:
                raise AssertionError("Expected grim to be called with -g in tests")
            geometry = self._parse_geometry(args[args.index("-g") + 1])
            scale = 1.25 if geometry["x"] < 2048 else 1.0
            out_w = max(1, round(geometry["width"] * scale))
            out_h = max(1, round(geometry["height"] * scale))
            output_path = Path(args[-1])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (out_w, out_h), color=(12, 34, 56)).save(output_path, format="PNG")
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


def test_hyprctl_infer_mixed_scale_dual_monitor_produces_layout_desktop_bounds() -> None:
    coordinate_map = resolve_hyprctl_infer({"monitors": MIXED_SCALE_TOPOLOGY_FIXTURE["monitors"]})
    assert coordinate_map.backend == "hyprctl-infer"
    assert coordinate_map.desktop_layout_bounds.model_dump() == {"x": 0, "y": 0, "width": 3968, "height": 1280}

    edp = next(monitor for monitor in coordinate_map.monitors if monitor.name == "eDP-1")
    assert edp.layout_bounds.model_dump() == {"x": 0, "y": 0, "width": 2048, "height": 1280}
    assert edp.pixel_ratio.model_dump() == {"x": 1.25, "y": 1.25}
    assert coordinate_map.confidence >= 0.8


def test_capture_metadata_includes_mapping_and_pixel_ratio(tmp_path: Path) -> None:
    runner = FakeMixedScaleRunner()
    write_config(tmp_path / "config.toml", coordinates_mode="hyprctl-infer")
    config = load_runtime_config(tmp_path / "config.toml")
    resolver = lambda name: f"/usr/bin/{name}"

    runtime = WispHandRuntime(
        config=config,
        command_runner=runner,
        hyprland_adapter=HyprlandAdapter(runner=runner, env={"HYPRLAND_INSTANCE_SIGNATURE": "fixture"}),
        capture_engine=CaptureEngine(
            artifact_store=CaptureArtifactStore(base_dir=config.paths.capture_dir),
            runner=runner,
            binary_resolver=resolver,
        ),
    )

    opened = runtime.open_session(
        scope_type="region",
        scope_target={"x": 0, "y": 0, "width": 120, "height": 120},
        armed=False,
        dry_run=False,
        ttl_seconds=60,
    )
    try:
        captured = runtime.capture_screen(session_id=opened["session_id"], target="scope", inline=False)
    finally:
        runtime.close_session(session_id=opened["session_id"])

    assert captured["source_coordinate_space"] == "layout_px"
    assert captured["image_coordinate_space"] == "image_px"
    assert captured["mapping"]["kind"] == "single"
    assert captured["pixel_ratio_x"] == 1.25
    assert captured["pixel_ratio_y"] == 1.25

    metadata = CaptureArtifactStore(base_dir=config.paths.capture_dir).load_metadata(str(captured["capture_id"]))
    assert metadata["pixel_ratio_x"] == 1.25
    assert metadata["mapping"]["kind"] == "single"


def test_pointer_dispatch_uses_layout_bounds_extent(tmp_path: Path) -> None:
    class FakeInputBackend:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def move_pointer(self, *, x: int, y: int, desktop_bounds: dict[str, int]) -> None:
            self.calls.append({"x": x, "y": y, "desktop_bounds": desktop_bounds})

        def click_pointer(self, *, x: int, y: int, button: str, desktop_bounds: dict[str, int]) -> None:  # noqa: ARG002
            self.calls.append({"x": x, "y": y, "desktop_bounds": desktop_bounds})

        def drag_pointer(self, *args, **kwargs) -> None:  # noqa: ANN001, D401, ARG002
            raise AssertionError("not used")

        def scroll_pointer(self, *args, **kwargs) -> None:  # noqa: ANN001, D401, ARG002
            raise AssertionError("not used")

        def type_text(self, *args, **kwargs) -> None:  # noqa: ANN001, D401, ARG002
            raise AssertionError("not used")

        def press_keys(self, *args, **kwargs) -> None:  # noqa: ANN001, D401, ARG002
            raise AssertionError("not used")

    single_monitor_topology = {
        "monitors": [
            {
                "id": 0,
                "name": "eDP-1",
                "x": 0,
                "y": 0,
                "width": 2560,
                "height": 1600,
                "scale": 1.25,
            }
        ],
        "workspaces": [],
        "activeworkspace": {},
        "activewindow": {},
        "clients": [],
        "cursorpos": {"x": 10, "y": 10},
    }

    class FakeSingleMonitorRunner(FakeMixedScaleRunner):
        def __call__(self, args: list[str]) -> CommandResult:
            self.calls.append(args)
            if args[:2] == ["hyprctl", "-j"]:
                key = args[2]
                return CommandResult(args=args, stdout=json.dumps(single_monitor_topology[key]), stderr="", returncode=0)
            return super().__call__(args)

    runner = FakeSingleMonitorRunner()
    write_config(tmp_path / "config.toml", coordinates_mode="hyprctl-infer")
    backend = FakeInputBackend()
    runtime = WispHandRuntime(
        config=load_runtime_config(tmp_path / "config.toml"),
        command_runner=runner,
        hyprland_adapter=HyprlandAdapter(runner=runner, env={"HYPRLAND_INSTANCE_SIGNATURE": "fixture"}),
        input_backend=backend,
    )

    opened = runtime.open_session(
        scope_type="region",
        scope_target={"x": 0, "y": 0, "width": 200, "height": 200},
        armed=True,
        dry_run=False,
        ttl_seconds=60,
    )
    try:
        runtime.pointer_move(session_id=opened["session_id"], x=10, y=10)
    finally:
        runtime.close_session(session_id=opened["session_id"])

    assert backend.calls[0]["desktop_bounds"]["width"] == 2048
    assert backend.calls[0]["desktop_bounds"]["height"] == 1280


def test_vision_locate_maps_candidates_to_scope_using_pixel_ratio(tmp_path: Path) -> None:
    class FakeOllamaTransport:
        def __init__(self, response: dict[str, Any]) -> None:
            self.calls: list[dict[str, Any]] = []
            self.response = response

        def __call__(self, *, url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
            self.calls.append({"url": url, "payload": payload, "timeout": timeout})
            return self.response

    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[server]
transport = "stdio"

[paths]
state_dir = "./state"
audit_file = "./state/audit.jsonl"
runtime_log_file = "./state/runtime.jsonl"
capture_dir = "./state/captures"

[vision]
mode = "assist"
model = "llava"
base_url = "http://127.0.0.1:11434"
timeout_seconds = 2.5
max_image_edge = 512
max_tokens = 128
max_concurrency = 1
""".strip(),
        encoding="utf-8",
    )
    runtime = WispHandRuntime(
        config=load_runtime_config(config_path),
        ollama_transport=FakeOllamaTransport(
            response={
                "response": json.dumps(
                    {
                        "candidates": [
                            {
                                "x": 25,
                                "y": 50,
                                "width": 50,
                                "height": 25,
                                "confidence": 0.8,
                                "reason": "matches the button label",
                            }
                        ]
                    }
                )
            }
        ),
    )

    capture_dir = runtime.config.paths.capture_dir
    capture_id = "cap-scale"
    image_path = capture_dir / f"{capture_id}.png"
    metadata_path = capture_dir / f"{capture_id}.json"
    capture_dir.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (150, 100), color=(0, 0, 0)).save(image_path, format="PNG")
    CaptureArtifactStore(base_dir=capture_dir).write_metadata(
        metadata_path=metadata_path,
        payload={
            "capture_id": capture_id,
            "scope": {
                "type": "region",
                "target": {"x": 0, "y": 0, "width": 120, "height": 80},
                "coordinate_space": {"origin": "scope", "units": "px", "relative_to": "region"},
                "constraints": {"input_relative": True},
            },
            "target": "scope",
            "width": 150,
            "height": 100,
            "mime_type": "image/png",
            "created_at": "2026-03-09T00:00:00+00:00",
            "source_bounds": {"x": 0, "y": 0, "width": 120, "height": 80},
            "source_coordinate_space": "layout_px",
            "image_coordinate_space": "image_px",
            "pixel_ratio_x": 1.25,
            "pixel_ratio_y": 1.25,
            "mapping": {"kind": "single", "monitors": []},
            "downscale": None,
        },
    )

    server = WispHandServer(runtime)

    async def run_test() -> None:
        result = await server.mcp.call_tool(
            "wisp_hand.vision.locate",
            {"capture_id": capture_id, "target": "submit", "space": "both"},
        )
        assert result.isError is False
        payload = result.structuredContent
        assert payload["candidates_image"] == [
            {
                "x": 25,
                "y": 50,
                "width": 50,
                "height": 25,
                "confidence": 0.8,
                "reason": "matches the button label",
            }
        ]
        assert payload["candidates_scope"] == [
            {
                "x": 20,
                "y": 40,
                "width": 40,
                "height": 20,
                "confidence": 0.8,
                "reason": "matches the button label",
            }
        ]

    asyncio.run(run_test())
