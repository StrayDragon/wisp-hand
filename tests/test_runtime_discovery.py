from __future__ import annotations

from pathlib import Path

from wisp_hand.capabilities import DependencyProbe
from wisp_hand.config import load_runtime_config
from wisp_hand.discovery import build_discovery_report


def write_config(path: Path, contents: str) -> Path:
    path.write_text(contents.strip(), encoding="utf-8")
    return path


def test_discovery_ready_stdio_and_network_transport(tmp_path: Path) -> None:
    config = load_runtime_config(
        write_config(
            tmp_path / "config.toml",
            """
[server]
transport = "stdio"

[paths]
state_dir = "./state"
audit_file = "./state/audit.jsonl"
runtime_log_file = "./state/runtime.jsonl"
""",
        )
    )
    probe = DependencyProbe(
        required_binaries=["hyprctl", "grim", "slurp"],
        optional_binaries=["wtype"],
        binary_resolver=lambda name: f"/usr/bin/{name}",
        env={"HYPRLAND_INSTANCE_SIGNATURE": "fixture"},
    )

    report = build_discovery_report(config=config, dependency_probe=probe, include_path_checks=True)
    assert report["status"] == "ready"
    assert report["transport"] == "stdio"
    assert report["host"] is None
    assert report["port"] is None
    assert report["paths_writable"]["state_dir"] is True
    assert report["paths_writable"]["capture_dir"] is True
    assert report["missing_binaries"] == []
    assert report["missing_optional"] == []

    net_config = config.model_copy(update={"server": config.server.model_copy(update={"transport": "sse", "port": 8123})})
    net_report = build_discovery_report(config=net_config, dependency_probe=probe, include_path_checks=True)
    assert net_report["status"] == "ready"
    assert net_report["transport"] == "sse"
    assert net_report["host"] == "127.0.0.1"
    assert net_report["port"] == 8123


def test_discovery_blocked_when_required_binaries_missing(tmp_path: Path) -> None:
    config = load_runtime_config(
        write_config(
            tmp_path / "config.toml",
            """
[server]
transport = "stdio"

[paths]
state_dir = "./state"
audit_file = "./state/audit.jsonl"
runtime_log_file = "./state/runtime.jsonl"
""",
        )
    )
    probe = DependencyProbe(
        required_binaries=["hyprctl", "grim", "slurp"],
        optional_binaries=["wtype"],
        binary_resolver=lambda name: None if name == "hyprctl" else f"/usr/bin/{name}",
        env={"HYPRLAND_INSTANCE_SIGNATURE": "fixture"},
    )

    report = build_discovery_report(config=config, dependency_probe=probe, include_path_checks=True)
    assert report["status"] == "blocked"
    assert report["missing_binaries"] == ["hyprctl"]
    assert any(issue.get("severity") == "blocking" for issue in report["issues"])

