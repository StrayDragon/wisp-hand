from __future__ import annotations

import json
from pathlib import Path

from wisp_hand.infra.config import load_runtime_config
from wisp_hand.infra.observability import get_logger, init_logging
from wisp_hand.app.runtime import WispHandRuntime


def write_config(
    path: Path,
    *,
    transport: str = "stdio",
    console_enabled: bool = False,
    file_enabled: bool = True,
    allow_sensitive: bool = False,
) -> None:
    path.write_text(
        f"""
[server]
transport = "{transport}"

[paths]
state_dir = "./state"
audit_file = "./state/audit.jsonl"
runtime_log_file = "./state/runtime.jsonl"
capture_dir = "./state/captures"

[logging]
level = "INFO"
allow_sensitive = {str(allow_sensitive).lower()}

[logging.console]
enabled = {str(console_enabled).lower()}
format = "plain"

[logging.file]
enabled = {str(file_enabled).lower()}
format = "json"
""".strip(),
        encoding="utf-8",
    )


def test_runtime_json_lines_include_required_fields(tmp_path: Path) -> None:
    write_config(tmp_path / "config.toml")
    config = load_runtime_config(tmp_path / "config.toml")
    runtime = WispHandRuntime(config=config)

    runtime.capabilities()
    runtime.open_session(
        scope_type="region",
        scope_target={"x": 1, "y": 2, "width": 3, "height": 4},
        armed=None,
        dry_run=None,
        ttl_seconds=30,
    )

    log_path = config.paths.runtime_log_file
    assert log_path is not None and log_path.exists()

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line]
    assert entries
    for entry in entries:
        assert "timestamp" in entry
        assert "level" in entry
        assert "event" in entry
        assert "component" in entry

    tool_calls = [
        entry
        for entry in entries
        if entry.get("event") == "tool.call.ok" and entry.get("tool_name") == "wisp_hand.capabilities"
    ]
    assert tool_calls
    assert tool_calls[0]["status"] == "ok"
    assert isinstance(tool_calls[0]["latency_ms"], int)


def test_stdio_transport_never_writes_logs_to_stdout(tmp_path: Path, capsys) -> None:
    write_config(tmp_path / "config.toml", transport="stdio", console_enabled=True, file_enabled=False)
    config = load_runtime_config(tmp_path / "config.toml")

    init_logging(config)
    get_logger("test").info("stdio.smoke", answer=42)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err


def test_default_scrubbing_hides_keyboard_text_and_inline_base64(tmp_path: Path) -> None:
    write_config(tmp_path / "config.toml", console_enabled=False, file_enabled=True, allow_sensitive=False)
    config = load_runtime_config(tmp_path / "config.toml")
    runtime = WispHandRuntime(config=config)

    session = runtime.open_session(
        scope_type="region",
        scope_target={"x": 0, "y": 0, "width": 10, "height": 10},
        armed=True,
        dry_run=True,
        ttl_seconds=30,
    )
    runtime.keyboard_type(session_id=session["session_id"], text="super-secret")

    base64_payload = "AAAABASE64XYZ"
    get_logger("test").info("vision.payload", inline_image=base64_payload)
    runtime._audit_logger.record(  # noqa: SLF001 - test verifies audit scrubbing behaviour
        {
            "timestamp": "2026-03-10T00:00:00+00:00",
            "tool_name": "wisp_hand.vision.describe",
            "status": "ok",
            "latency_ms": 1,
            "result": {"inline_image": base64_payload},
        }
    )

    log_path = config.paths.runtime_log_file
    assert log_path is not None and log_path.exists()
    runtime_log_text = log_path.read_text(encoding="utf-8")
    assert "super-secret" not in runtime_log_text
    assert base64_payload not in runtime_log_text

    audit_path = config.paths.audit_file
    assert audit_path is not None and audit_path.exists()
    audit_text = audit_path.read_text(encoding="utf-8")
    assert "super-secret" not in audit_text
    assert base64_payload not in audit_text
