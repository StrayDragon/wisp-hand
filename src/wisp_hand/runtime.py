from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from wisp_hand.audit import AuditLogger
from wisp_hand.capabilities import DependencyProbe
from wisp_hand.capture import CaptureArtifactStore, CaptureEngine, CaptureTarget
from wisp_hand.command import CommandRunner
from wisp_hand.config import RuntimeConfig, load_runtime_config
from wisp_hand.errors import WispHandError, internal_error
from wisp_hand.hyprland import HyprlandAdapter
from wisp_hand.models import (
    AuditRecord,
    CapabilityResult,
    JSONValue,
    ScopeEnvelope,
    ScopeType,
    SessionCloseResult,
    SessionOpenResult,
)
from wisp_hand.scope import normalize_scope
from wisp_hand.session import SessionStore

IMPLEMENTED_TOOLS = [
    "hand.capabilities",
    "hand.session.open",
    "hand.session.close",
    "hand.desktop.get_topology",
    "hand.cursor.get_position",
    "hand.capture.screen",
]


class WispHandRuntime:
    def __init__(
        self,
        *,
        config: RuntimeConfig,
        session_store: SessionStore | None = None,
        dependency_probe: DependencyProbe | None = None,
        audit_logger: AuditLogger | None = None,
        command_runner: CommandRunner | None = None,
        hyprland_adapter: HyprlandAdapter | None = None,
        capture_engine: CaptureEngine | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._command_runner = command_runner or CommandRunner()
        self._session_store = session_store or SessionStore(
            default_ttl_seconds=config.session.default_ttl_seconds,
            max_ttl_seconds=config.session.max_ttl_seconds,
            now_provider=self._now_provider,
        )
        self._dependency_probe = dependency_probe or DependencyProbe(
            required_binaries=config.dependencies.required_binaries,
            optional_binaries=config.dependencies.optional_binaries,
        )
        self._hyprland = hyprland_adapter or HyprlandAdapter(runner=self._command_runner)
        self._capture_engine = capture_engine or CaptureEngine(
            artifact_store=CaptureArtifactStore(base_dir=config.paths.capture_dir),
            runner=self._command_runner,
            now_provider=self._now_provider,
        )
        self._audit_logger = audit_logger or AuditLogger(
            text_log_file=config.paths.text_log_file,
            audit_file=config.paths.audit_file,
        )

    @classmethod
    def from_config_path(cls, config_path: str | None = None) -> "WispHandRuntime":
        path = None if config_path is None else Path(config_path)
        return cls(config=load_runtime_config(path))

    def capabilities(self) -> CapabilityResult:
        return self._run_tool(
            "hand.capabilities",
            action=lambda: self._dependency_probe.report(
                config_path=str(self.config.config_path),
                implemented_tools=IMPLEMENTED_TOOLS,
            ),
        )

    def open_session(
        self,
        *,
        scope_type: ScopeType,
        scope_target: JSONValue | None,
        armed: bool | None,
        dry_run: bool | None,
        ttl_seconds: int | None,
    ) -> SessionOpenResult:
        requested_scope = normalize_scope(scope_type, scope_target)

        def action() -> SessionOpenResult:
            record = self._session_store.create_session(
                scope=requested_scope,
                armed=self.config.safety.default_armed if armed is None else armed,
                dry_run=self.config.safety.default_dry_run if dry_run is None else dry_run,
                ttl_seconds=ttl_seconds,
            )
            return {
                "session_id": record.session_id,
                "scope": record.scope,
                "armed": record.armed,
                "dry_run": record.dry_run,
                "expires_at": record.expires_at.isoformat(),
            }

        return self._run_tool(
            "hand.session.open",
            action=action,
            scope=requested_scope,
        )

    def close_session(self, *, session_id: str) -> SessionCloseResult:
        def action() -> SessionCloseResult:
            record = self._session_store.close_session(session_id)
            return {
                "session_id": record.session_id,
                "closed": True,
                "closed_at": self._now_provider().isoformat(),
            }

        return self._run_tool(
            "hand.session.close",
            action=action,
            session_id=session_id,
        )

    def get_topology(self) -> JSONValue:
        return self._run_tool(
            "hand.desktop.get_topology",
            action=self._hyprland.get_topology,
        )

    def get_cursor_position(self, *, session_id: str) -> JSONValue:
        session = self._session_store.get_session(session_id)

        def action() -> JSONValue:
            topology = self._hyprland.get_topology()
            cursor = self._hyprland.get_cursor_position()
            relative = self._hyprland.relative_position(cursor=cursor, scope=session.scope, topology=topology)
            return {
                "x": cursor["x"],
                "y": cursor["y"],
                "scope_x": relative["scope_x"],
                "scope_y": relative["scope_y"],
            }

        return self._run_tool(
            "hand.cursor.get_position",
            action=action,
            session_id=session_id,
            scope=session.scope,
        )

    def capture_screen(
        self,
        *,
        session_id: str,
        target: CaptureTarget,
        inline: bool = False,
        with_cursor: bool = False,
        downscale: float | None = None,
    ) -> JSONValue:
        session = self._session_store.get_session(session_id)

        def action() -> JSONValue:
            topology = self._hyprland.get_topology()
            return self._capture_engine.capture(
                target=target,
                scope=session.scope,
                topology=topology,
                bounds_resolver=self._hyprland.scope_bounds,
                inline=inline,
                with_cursor=with_cursor,
                downscale=downscale,
            )

        return self._run_tool(
            "hand.capture.screen",
            action=action,
            session_id=session_id,
            scope=session.scope,
        )

    def _run_tool(
        self,
        tool_name: str,
        *,
        action: Callable[[], JSONValue],
        session_id: str | None = None,
        scope: ScopeEnvelope | None = None,
    ) -> JSONValue:
        started = perf_counter()
        try:
            result = action()
        except WispHandError as exc:
            self._audit_logger.record(
                self._build_audit_record(
                    tool_name=tool_name,
                    status="error",
                    latency_ms=self._elapsed_ms(started),
                    session_id=session_id,
                    scope=scope,
                    error=exc.to_payload(),
                )
            )
            raise
        except Exception as exc:  # pragma: no cover - defensive wrapper
            error = internal_error(str(exc))
            self._audit_logger.record(
                self._build_audit_record(
                    tool_name=tool_name,
                    status="error",
                    latency_ms=self._elapsed_ms(started),
                    session_id=session_id,
                    scope=scope,
                    error=error.to_payload(),
                )
            )
            raise error from exc

        payload_scope = scope
        payload_session_id = session_id
        if isinstance(result, dict):
            payload_scope = result.get("scope", payload_scope)  # type: ignore[assignment]
            payload_session_id = result.get("session_id", payload_session_id)  # type: ignore[assignment]

        self._audit_logger.record(
            self._build_audit_record(
                tool_name=tool_name,
                status="ok",
                latency_ms=self._elapsed_ms(started),
                session_id=payload_session_id,
                scope=payload_scope,
                result=result,
            )
        )
        return result

    def _build_audit_record(
        self,
        *,
        tool_name: str,
        status: str,
        latency_ms: int,
        session_id: str | None = None,
        scope: ScopeEnvelope | None = None,
        result: JSONValue | None = None,
        error: dict[str, JSONValue] | None = None,
    ) -> AuditRecord:
        payload: AuditRecord = {
            "timestamp": self._now_provider().isoformat(),
            "tool_name": tool_name,
            "status": status,  # type: ignore[typeddict-item]
            "latency_ms": latency_ms,
        }
        payload["session_id"] = session_id
        payload["scope"] = scope
        if result is not None:
            payload["result"] = result
        if error is not None:
            payload["error"] = error
        return payload

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(0, round((perf_counter() - started) * 1000))
