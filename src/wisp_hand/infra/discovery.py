from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path
from typing import Any, Literal

from wisp_hand.capabilities.service import DependencyProbe
from wisp_hand.infra.config import RuntimeConfig
from wisp_hand.shared.errors import WispHandError
from wisp_hand.tooling import IMPLEMENTED_TOOLS


DiscoveryStatus = Literal["ready", "blocked"]


@dataclass(frozen=True, slots=True)
class DiscoveryIssue:
    severity: Literal["blocking", "warning"]
    error: WispHandError

    def to_payload(self) -> dict[str, Any]:
        payload = self.error.to_payload()
        payload["severity"] = self.severity
        return payload


def runtime_version() -> str:
    try:
        return pkg_version("wisp-hand")
    except PackageNotFoundError:
        return "unknown"
    except Exception:  # pragma: no cover - defensive
        return "unknown"
    return "unknown"


def _check_dir_writable(path: Path) -> WispHandError | None:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".wisp_hand_write_check_", dir=path, delete=True) as handle:
            handle.write(b"ok")
            handle.flush()
    except Exception as exc:
        return WispHandError(
            "invalid_config",
            "Path is not writable",
            {"path": str(path), "error": repr(exc)},
        )
    return None


def _check_file_parent_writable(path: Path) -> WispHandError | None:
    return _check_dir_writable(path.parent)


def build_discovery_report(
    *,
    config: RuntimeConfig,
    dependency_probe: DependencyProbe | None = None,
    runtime_instance_id: str | None = None,
    started_at: str | None = None,
    include_path_checks: bool = True,
) -> dict[str, Any]:
    probe = dependency_probe or DependencyProbe(
        required_binaries=config.dependencies.required_binaries,
        optional_binaries=config.dependencies.optional_binaries,
    )
    deps = probe.report(config_path=str(config.config_path), implemented_tools=IMPLEMENTED_TOOLS)
    deps["vision_available"] = (
        config.vision.mode == "assist" and bool(config.vision.model) and bool(config.vision.base_url)
    )

    # Normalize optional-missing for discovery (DependencyProbe.report returns this field).
    missing_optional = deps.get("missing_optional")
    if not isinstance(missing_optional, list):
        missing_optional = []

    issues: list[DiscoveryIssue] = []

    if deps.get("hyprland_detected") is not True:
        issues.append(
            DiscoveryIssue(
                "blocking",
                WispHandError(
                    "unsupported_environment",
                    "Hyprland environment was not detected",
                    {
                        "HYPRLAND_INSTANCE_SIGNATURE": os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"),
                        "XDG_SESSION_TYPE": os.environ.get("XDG_SESSION_TYPE"),
                        "WAYLAND_DISPLAY": os.environ.get("WAYLAND_DISPLAY"),
                    },
                ),
            )
        )

    missing_required = deps.get("missing_binaries")
    if isinstance(missing_required, list) and missing_required:
        issues.append(
            DiscoveryIssue(
                "blocking",
                WispHandError(
                    "dependency_missing",
                    "Required binaries are missing",
                    {"missing_binaries": list(missing_required)},
                ),
            )
        )

    if isinstance(missing_optional, list) and missing_optional:
        issues.append(
            DiscoveryIssue(
                "warning",
                WispHandError(
                    "dependency_missing",
                    "Optional binaries are missing",
                    {"missing_optional": list(missing_optional)},
                ),
            )
        )

    paths = {
        "state_dir": str(config.paths.state_dir),
        "capture_dir": str(config.paths.capture_dir),
        "audit_file": str(config.paths.audit_file) if config.paths.audit_file is not None else None,
        "runtime_log_file": str(config.paths.runtime_log_file) if config.paths.runtime_log_file is not None else None,
    }

    paths_writable: dict[str, bool] = {}
    if include_path_checks:
        checks: list[tuple[str, WispHandError | None]] = [
            ("state_dir", _check_dir_writable(config.paths.state_dir)),
            ("capture_dir", _check_dir_writable(config.paths.capture_dir)),
        ]
        if config.paths.audit_file is not None:
            checks.append(("audit_file", _check_file_parent_writable(config.paths.audit_file)))
        if config.paths.runtime_log_file is not None:
            checks.append(("runtime_log_file", _check_file_parent_writable(config.paths.runtime_log_file)))

        for key, err in checks:
            paths_writable[key] = err is None
            if err is not None:
                issues.append(DiscoveryIssue("blocking", err))

    status: DiscoveryStatus = "ready" if not any(issue.severity == "blocking" for issue in issues) else "blocked"

    retention = {
        "captures": {
            "max_age_seconds": config.retention.captures.max_age_seconds,
            "max_total_bytes": config.retention.captures.max_total_bytes,
        },
        "audit": {
            "max_bytes": config.retention.audit.max_bytes,
            "backup_count": config.retention.audit.backup_count,
        },
        "runtime_log": {
            "max_bytes": config.retention.runtime_log.max_bytes,
            "backup_count": config.retention.runtime_log.backup_count,
        },
    }

    report: dict[str, Any] = {
        "status": status,
        "version": runtime_version(),
        "runtime_instance_id": runtime_instance_id,
        "started_at": started_at,
        "transport": config.server.transport,
        "host": config.server.host if config.server.transport != "stdio" else None,
        "port": config.server.port if config.server.transport != "stdio" else None,
        "config_path": str(config.config_path),
        "paths": paths,
        "paths_writable": paths_writable,
        "retention": retention,
        "issues": [issue.to_payload() for issue in issues],
        # Keep the existing capabilities surface at the top level for clients.
        **deps,
    }

    # Ensure JSON-serializability.
    json.dumps(report, ensure_ascii=True, sort_keys=True)
    return report
