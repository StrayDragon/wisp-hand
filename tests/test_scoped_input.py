from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from wisp_hand.command import CommandResult
from wisp_hand.config import load_runtime_config
from wisp_hand.errors import WispHandError
from wisp_hand.hyprland import HyprlandAdapter
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


class FakeTicker:
    def __init__(self, current: float = 0.0) -> None:
        self.current = current

    def now(self) -> float:
        return self.current

    def advance(self, *, seconds: float) -> None:
        self.current += seconds


class FakeHyprlandRunner:
    def __call__(self, args: list[str]) -> CommandResult:
        if args[:2] != ["hyprctl", "-j"]:
            raise AssertionError(f"Unexpected command: {args}")
        return CommandResult(
            args=args,
            stdout=json.dumps(TOPOLOGY_FIXTURE[args[2]]),
            stderr="",
            returncode=0,
        )


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


def write_config(
    path: Path,
    *,
    max_actions_per_window: int = 16,
    rate_limit_window_seconds: float = 1.0,
    dangerous_shortcuts: list[str] | None = None,
) -> None:
    shortcuts = dangerous_shortcuts or ["ctrl+alt+delete"]
    serialized_shortcuts = ", ".join(f'"{item}"' for item in shortcuts)
    path.write_text(
        f"""
[server]
transport = "stdio"

[paths]
state_dir = "./state"
audit_file = "./state/audit.jsonl"
runtime_log_file = "./state/runtime.jsonl"

[session]
default_ttl_seconds = 30
max_ttl_seconds = 120

[safety]
default_armed = false
default_dry_run = false
max_actions_per_window = {max_actions_per_window}
rate_limit_window_seconds = {rate_limit_window_seconds}
dangerous_shortcuts = [{serialized_shortcuts}]
""".strip(),
        encoding="utf-8",
    )


def build_runtime(
    tmp_path: Path,
    *,
    input_backend: FakeInputBackend | None = None,
    ticker: FakeTicker | None = None,
    max_actions_per_window: int = 16,
    dangerous_shortcuts: list[str] | None = None,
) -> tuple[WispHandRuntime, FakeInputBackend]:
    write_config(
        tmp_path / "config.toml",
        max_actions_per_window=max_actions_per_window,
        dangerous_shortcuts=dangerous_shortcuts,
    )
    backend = input_backend or FakeInputBackend()
    runtime = WispHandRuntime(
        config=load_runtime_config(tmp_path / "config.toml"),
        hyprland_adapter=HyprlandAdapter(
            runner=FakeHyprlandRunner(),
            env={"HYPRLAND_INSTANCE_SIGNATURE": "fixture"},
        ),
        input_backend=backend,
        monotonic_provider=(ticker.now if ticker is not None else None),
    )
    return runtime, backend


def test_input_tools_return_structured_denials_and_scope_mapping(tmp_path: Path) -> None:
    runtime, _ = build_runtime(tmp_path)
    server = WispHandServer(runtime)
    unarmed = runtime.open_session(
        scope_type="region",
        scope_target={"x": 100, "y": 200, "width": 300, "height": 300},
        armed=None,
        dry_run=None,
        ttl_seconds=30,
    )
    armed = runtime.open_session(
        scope_type="region",
        scope_target={"x": 100, "y": 200, "width": 300, "height": 300},
        armed=True,
        dry_run=None,
        ttl_seconds=30,
    )

    async def run_test() -> None:
        not_armed = await server.mcp.call_tool(
            "hand.pointer.move",
            {"session_id": unarmed["session_id"], "x": 10, "y": 20},
        )
        assert not_armed.isError is True
        assert not_armed.structuredContent["code"] == "session_not_armed"

        out_of_scope = await server.mcp.call_tool(
            "hand.pointer.click",
            {"session_id": armed["session_id"], "x": 301, "y": 10},
        )
        assert out_of_scope.isError is True
        assert out_of_scope.structuredContent["code"] == "scope_violation"

    asyncio.run(run_test())


def test_dry_run_and_audit_cover_ok_denied_and_error(tmp_path: Path) -> None:
    runtime, backend = build_runtime(tmp_path)
    dry_run_session = runtime.open_session(
        scope_type="region",
        scope_target={"x": 100, "y": 200, "width": 300, "height": 300},
        armed=True,
        dry_run=True,
        ttl_seconds=30,
    )

    result = runtime.pointer_click(session_id=dry_run_session["session_id"], x=5, y=6)
    assert result["dispatch_state"] == "dry_run"
    assert backend.calls == []

    runtime.trigger_emergency_stop(reason="manual")
    with pytest.raises(WispHandError) as denied_exc:
        runtime.keyboard_type(session_id=dry_run_session["session_id"], text="hello")
    assert denied_exc.value.code == "policy_denied"
    runtime.clear_emergency_stop()

    with pytest.raises(WispHandError) as missing_exc:
        runtime.pointer_move(session_id="missing", x=1, y=1)
    assert missing_exc.value.code == "session_not_found"

    audit_path = runtime.config.paths.audit_file
    assert audit_path is not None and audit_path.exists()
    entries = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    statuses = {entry["status"] for entry in entries if entry["tool_name"].startswith("hand.")}
    assert {"ok", "denied", "error"} <= statuses


def test_policy_rate_limit_and_dangerous_shortcut_deny(tmp_path: Path) -> None:
    ticker = FakeTicker()
    runtime, _ = build_runtime(
        tmp_path,
        ticker=ticker,
        max_actions_per_window=2,
        dangerous_shortcuts=["ctrl+alt+delete"],
    )
    session = runtime.open_session(
        scope_type="region",
        scope_target={"x": 100, "y": 200, "width": 300, "height": 300},
        armed=True,
        dry_run=None,
        ttl_seconds=30,
    )

    runtime.pointer_move(session_id=session["session_id"], x=1, y=1)
    runtime.pointer_move(session_id=session["session_id"], x=2, y=2)

    with pytest.raises(WispHandError) as rate_limit_exc:
        runtime.pointer_move(session_id=session["session_id"], x=3, y=3)
    assert rate_limit_exc.value.code == "policy_denied"
    assert rate_limit_exc.value.details["reason"] == "rate_limit"

    ticker.advance(seconds=1.0)

    with pytest.raises(WispHandError) as shortcut_exc:
        runtime.keyboard_press(session_id=session["session_id"], keys=["ctrl", "alt", "delete"])
    assert shortcut_exc.value.code == "policy_denied"
    assert shortcut_exc.value.details["reason"] == "dangerous_shortcut"


def test_input_actions_execute_repeatedly_with_stable_payloads(tmp_path: Path) -> None:
    runtime, backend = build_runtime(tmp_path)
    session = runtime.open_session(
        scope_type="region",
        scope_target={"x": 100, "y": 200, "width": 300, "height": 300},
        armed=True,
        dry_run=None,
        ttl_seconds=30,
    )

    for _ in range(2):
        move = runtime.pointer_move(session_id=session["session_id"], x=5, y=6)
        click = runtime.pointer_click(session_id=session["session_id"], x=10, y=20, button="right")
        drag = runtime.pointer_drag(
            session_id=session["session_id"],
            start_x=0,
            start_y=0,
            end_x=299,
            end_y=299,
        )
        scroll = runtime.pointer_scroll(
            session_id=session["session_id"],
            x=25,
            y=30,
            delta_x=1,
            delta_y=-2,
        )
        typed = runtime.keyboard_type(session_id=session["session_id"], text="Hi")
        pressed = runtime.keyboard_press(session_id=session["session_id"], keys=["ctrl", "k"])

        assert move["dispatch_state"] == "executed"
        assert move["action"]["absolute_position"] == {"x": 105, "y": 206}
        assert click["action"]["absolute_position"] == {"x": 110, "y": 220}
        assert drag["action"]["absolute_end"] == {"x": 399, "y": 499}
        assert scroll["action"]["absolute_position"] == {"x": 125, "y": 230}
        assert typed["action"]["text"] == "Hi"
        assert pressed["action"]["keys"] == ["ctrl", "k"]

    assert backend.calls == [
        ("move", {"x": 105, "y": 206, "desktop_bounds": {"x": 0, "y": 0, "width": 3200, "height": 1080}}),
        ("click", {"x": 110, "y": 220, "button": "right", "desktop_bounds": {"x": 0, "y": 0, "width": 3200, "height": 1080}}),
        ("drag", {"start_x": 100, "start_y": 200, "end_x": 399, "end_y": 499, "button": "left", "desktop_bounds": {"x": 0, "y": 0, "width": 3200, "height": 1080}}),
        ("scroll", {"x": 125, "y": 230, "delta_x": 1, "delta_y": -2, "desktop_bounds": {"x": 0, "y": 0, "width": 3200, "height": 1080}}),
        ("type", {"text": "Hi"}),
        ("press", {"keys": ["ctrl", "k"]}),
        ("move", {"x": 105, "y": 206, "desktop_bounds": {"x": 0, "y": 0, "width": 3200, "height": 1080}}),
        ("click", {"x": 110, "y": 220, "button": "right", "desktop_bounds": {"x": 0, "y": 0, "width": 3200, "height": 1080}}),
        ("drag", {"start_x": 100, "start_y": 200, "end_x": 399, "end_y": 499, "button": "left", "desktop_bounds": {"x": 0, "y": 0, "width": 3200, "height": 1080}}),
        ("scroll", {"x": 125, "y": 230, "delta_x": 1, "delta_y": -2, "desktop_bounds": {"x": 0, "y": 0, "width": 3200, "height": 1080}}),
        ("type", {"text": "Hi"}),
        ("press", {"keys": ["ctrl", "k"]}),
    ]
