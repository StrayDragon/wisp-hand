from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from wisp_hand.capabilities import DependencyProbe
from wisp_hand.config import load_runtime_config
from wisp_hand.errors import ConfigError, WispHandError
from wisp_hand.runtime import WispHandRuntime
from wisp_hand.server import WispHandServer
from wisp_hand.session import SessionStore


class FakeClock:
    def __init__(self, current: datetime | None = None) -> None:
        self.current = current or datetime(2026, 3, 9, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    def advance(self, *, seconds: int) -> None:
        self.current += timedelta(seconds=seconds)


def write_config(path: Path, contents: str) -> Path:
    path.write_text(contents, encoding="utf-8")
    return path


def load_test_config(tmp_path: Path) -> object:
    return load_runtime_config(
        write_config(
            tmp_path / "config.toml",
            """
[server]
transport = "stdio"

[paths]
state_dir = "./state"
audit_file = "./state/audit.jsonl"
runtime_log_file = "./state/runtime.jsonl"

[session]
default_ttl_seconds = 30
max_ttl_seconds = 120
""".strip(),
        )
    )


def test_load_runtime_config_resolves_relative_paths(tmp_path: Path) -> None:
    config = load_runtime_config(
        write_config(
            tmp_path / "config.toml",
            """
[server]
transport = "sse"

[paths]
state_dir = "./var/state"
audit_file = "./var/audit/audit.jsonl"
runtime_log_file = "./var/log/runtime.jsonl"

[logging]
level = "DEBUG"

[safety]
default_armed = true
default_dry_run = true
""".strip(),
        )
    )

    assert config.server.transport == "sse"
    assert config.logging.level == "DEBUG"
    assert config.safety.default_armed is True
    assert config.safety.default_dry_run is True
    assert config.paths.state_dir == (tmp_path / "var/state").resolve()
    assert config.paths.audit_file == (tmp_path / "var/audit/audit.jsonl").resolve()
    assert config.paths.runtime_log_file == (tmp_path / "var/log/runtime.jsonl").resolve()
    assert config.paths.capture_dir == (tmp_path / "var/state/captures").resolve()


def test_load_runtime_config_rejects_invalid_values(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path / "broken.toml",
        """
[server]
port = "invalid"
""".strip(),
    )

    with pytest.raises(ConfigError) as exc_info:
        load_runtime_config(config_path)

    assert exc_info.value.code == "invalid_config"
    assert exc_info.value.details["path"] == str(config_path.resolve())


def test_capabilities_reports_missing_binaries_without_crashing(tmp_path: Path) -> None:
    config = load_test_config(tmp_path)
    runtime = WispHandRuntime(
        config=config,
        dependency_probe=DependencyProbe(
            required_binaries=["hyprctl", "grim", "slurp"],
            optional_binaries=["wtype"],
            binary_resolver=lambda name: None if name == "hyprctl" else f"/usr/bin/{name}",
            env={"HYPRLAND_INSTANCE_SIGNATURE": "demo"},
        ),
    )

    result = runtime.capabilities()

    assert result["hyprland_detected"] is True
    assert result["capture_available"] is False
    assert result["input_available"] is False
    assert result["vision_available"] is False
    assert result["missing_binaries"] == ["hyprctl"]


def test_session_store_handles_expiry_and_close() -> None:
    clock = FakeClock()
    store = SessionStore(
        default_ttl_seconds=10,
        max_ttl_seconds=30,
        now_provider=clock.now,
    )
    scope = {
        "type": "desktop",
        "target": {"kind": "virtual-desktop"},
        "coordinate_space": {"origin": "scope", "units": "px", "relative_to": "desktop"},
        "constraints": {"input_relative": True},
    }

    record = store.create_session(scope=scope, armed=False, dry_run=False, ttl_seconds=5)
    assert store.get_session(record.session_id).session_id == record.session_id

    clock.advance(seconds=6)
    with pytest.raises(WispHandError) as expired_exc:
        store.get_session(record.session_id)
    assert expired_exc.value.code == "session_expired"

    fresh = store.create_session(scope=scope, armed=False, dry_run=False, ttl_seconds=5)
    store.close_session(fresh.session_id)
    with pytest.raises(WispHandError) as missing_exc:
        store.get_session(fresh.session_id)
    assert missing_exc.value.code == "session_not_found"


def test_server_registers_tools_and_returns_structured_output(tmp_path: Path) -> None:
    config = load_test_config(tmp_path)
    server = WispHandServer(WispHandRuntime(config=config))

    async def run_test() -> None:
        tools = await server.mcp.list_tools()
        tool_names = {tool.name for tool in tools}
        assert tool_names == {
            "wisp_hand.capabilities",
            "wisp_hand.session.open",
            "wisp_hand.session.close",
            "wisp_hand.desktop.get_topology",
            "wisp_hand.desktop.get_active_window",
            "wisp_hand.desktop.get_monitors",
            "wisp_hand.desktop.list_windows",
            "wisp_hand.cursor.get_position",
            "wisp_hand.capture.screen",
            "wisp_hand.wait",
            "wisp_hand.capture.diff",
            "wisp_hand.batch.run",
            "wisp_hand.vision.describe",
            "wisp_hand.vision.locate",
            "wisp_hand.pointer.move",
            "wisp_hand.pointer.click",
            "wisp_hand.pointer.drag",
            "wisp_hand.pointer.scroll",
            "wisp_hand.keyboard.type",
            "wisp_hand.keyboard.press",
        }

        result = await server.mcp.call_tool(
            "wisp_hand.session.open",
            {
                "scope_type": "region",
                "scope_target": {"x": 10, "y": 20, "width": 100, "height": 80},
                "ttl_seconds": 15,
            },
        )
        payload = result.structuredContent
        assert result.isError is False
        assert payload["scope"]["type"] == "region"
        assert payload["armed"] is False
        assert payload["dry_run"] is False
        assert result.content[0].type == "text"
        assert result.content[0].text == "ok"
        assert len(result.content[0].text) < 64

    asyncio.run(run_test())


def test_server_tool_content_stays_short_on_errors(tmp_path: Path) -> None:
    config = load_test_config(tmp_path)
    server = WispHandServer(WispHandRuntime(config=config))

    async def run_test() -> None:
        result = await server.mcp.call_tool("wisp_hand.session.close", {"session_id": "missing"})
        payload = result.structuredContent
        assert result.isError is True
        assert payload["code"] == "session_not_found"
        assert result.content[0].type == "text"
        assert result.content[0].text == "session_not_found: Session could not be found"
        assert "\n" not in result.content[0].text
        assert len(result.content[0].text) < 64

    asyncio.run(run_test())


def test_server_raises_structured_mcp_error_for_missing_session(tmp_path: Path) -> None:
    config = load_test_config(tmp_path)
    server = WispHandServer(WispHandRuntime(config=config))

    async def run_test() -> None:
        result = await server.mcp.call_tool("wisp_hand.session.close", {"session_id": "missing"})
        payload = result.structuredContent
        assert result.isError is True
        assert payload["code"] == "session_not_found"
        assert payload["details"]["session_id"] == "missing"

    asyncio.run(run_test())


def test_audit_logs_include_required_fields(tmp_path: Path) -> None:
    config = load_test_config(tmp_path)
    runtime = WispHandRuntime(config=config)

    runtime.capabilities()
    opened = runtime.open_session(
        scope_type="region",
        scope_target={"x": 1, "y": 2, "width": 3, "height": 4},
        armed=None,
        dry_run=None,
        ttl_seconds=12,
    )

    audit_path = config.paths.audit_file
    assert audit_path is not None and audit_path.exists()

    lines = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 2
    capability_record, session_record = lines

    assert capability_record["tool_name"] == "wisp_hand.capabilities"
    assert capability_record["status"] == "ok"
    assert "latency_ms" in capability_record

    assert session_record["tool_name"] == "wisp_hand.session.open"
    assert session_record["status"] == "ok"
    assert session_record["session_id"] == opened["session_id"]
    assert session_record["scope"]["type"] == "region"
    assert session_record["result"]["session_id"] == opened["session_id"]

    runtime_log = config.paths.runtime_log_file
    assert runtime_log is not None and runtime_log.exists()
