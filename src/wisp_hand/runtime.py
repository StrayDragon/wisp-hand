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
from wisp_hand.hyprland import HyprlandAdapter, desktop_bounds
from wisp_hand.input_backend import InputBackend, WaylandInputBackend
from wisp_hand.models import (
    AuditRecord,
    CapabilityResult,
    InputDispatchResult,
    JSONValue,
    PointerButton,
    ScopeEnvelope,
    ScopeType,
    SessionCloseResult,
    SessionOpenResult,
    SessionRecord,
)
from wisp_hand.policy import InputPolicy, normalize_key_name
from wisp_hand.scope import normalize_scope
from wisp_hand.session import SessionStore

IMPLEMENTED_TOOLS = [
    "hand.capabilities",
    "hand.session.open",
    "hand.session.close",
    "hand.desktop.get_topology",
    "hand.cursor.get_position",
    "hand.capture.screen",
    "hand.pointer.move",
    "hand.pointer.click",
    "hand.pointer.drag",
    "hand.pointer.scroll",
    "hand.keyboard.type",
    "hand.keyboard.press",
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
        input_backend: InputBackend | None = None,
        input_policy: InputPolicy | None = None,
        now_provider: Callable[[], datetime] | None = None,
        monotonic_provider: Callable[[], float] | None = None,
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
        self._input_backend = input_backend or WaylandInputBackend(runner=self._command_runner)
        self._input_policy = input_policy or InputPolicy(
            max_actions_per_window=config.safety.max_actions_per_window,
            rate_limit_window_seconds=config.safety.rate_limit_window_seconds,
            dangerous_shortcuts=config.safety.dangerous_shortcuts,
            monotonic_provider=monotonic_provider,
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
        def action() -> JSONValue:
            session = self._session_store.get_session(session_id)
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
        def action() -> JSONValue:
            session = self._session_store.get_session(session_id)
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
        )

    def pointer_move(self, *, session_id: str, x: int, y: int) -> InputDispatchResult:
        policy_action: dict[str, JSONValue] = {
            "kind": "pointer.move",
            "scope_position": {"x": x, "y": y},
        }
        return self._run_input_action(
            "hand.pointer.move",
            session_id=session_id,
            policy_action=policy_action,
            prepare=lambda session: self._prepare_pointer_target(
                session=session,
                kind="pointer.move",
                scope_x=x,
                scope_y=y,
            ),
            dispatch=lambda prepared: self._input_backend.move_pointer(
                x=int(prepared["absolute_position"]["x"]),  # type: ignore[index]
                y=int(prepared["absolute_position"]["y"]),  # type: ignore[index]
                desktop_bounds=prepared["desktop_bounds"],  # type: ignore[arg-type]
            ),
        )

    def pointer_click(
        self,
        *,
        session_id: str,
        x: int,
        y: int,
        button: PointerButton = "left",
    ) -> InputDispatchResult:
        normalized_button = self._normalize_button(button)
        policy_action: dict[str, JSONValue] = {
            "kind": "pointer.click",
            "button": normalized_button,
            "scope_position": {"x": x, "y": y},
        }
        return self._run_input_action(
            "hand.pointer.click",
            session_id=session_id,
            policy_action=policy_action,
            prepare=lambda session: self._prepare_pointer_target(
                session=session,
                kind="pointer.click",
                scope_x=x,
                scope_y=y,
                extra={"button": normalized_button},
            ),
            dispatch=lambda prepared: self._input_backend.click_pointer(
                x=int(prepared["absolute_position"]["x"]),  # type: ignore[index]
                y=int(prepared["absolute_position"]["y"]),  # type: ignore[index]
                button=normalized_button,
                desktop_bounds=prepared["desktop_bounds"],  # type: ignore[arg-type]
            ),
        )

    def pointer_drag(
        self,
        *,
        session_id: str,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        button: PointerButton = "left",
    ) -> InputDispatchResult:
        normalized_button = self._normalize_button(button)
        policy_action: dict[str, JSONValue] = {
            "kind": "pointer.drag",
            "button": normalized_button,
            "scope_start": {"x": start_x, "y": start_y},
            "scope_end": {"x": end_x, "y": end_y},
        }
        return self._run_input_action(
            "hand.pointer.drag",
            session_id=session_id,
            policy_action=policy_action,
            prepare=lambda session: self._prepare_pointer_drag(
                session=session,
                start_x=start_x,
                start_y=start_y,
                end_x=end_x,
                end_y=end_y,
                button=normalized_button,
            ),
            dispatch=lambda prepared: self._input_backend.drag_pointer(
                start_x=int(prepared["absolute_start"]["x"]),  # type: ignore[index]
                start_y=int(prepared["absolute_start"]["y"]),  # type: ignore[index]
                end_x=int(prepared["absolute_end"]["x"]),  # type: ignore[index]
                end_y=int(prepared["absolute_end"]["y"]),  # type: ignore[index]
                button=normalized_button,
                desktop_bounds=prepared["desktop_bounds"],  # type: ignore[arg-type]
            ),
        )

    def pointer_scroll(
        self,
        *,
        session_id: str,
        x: int,
        y: int,
        delta_x: int = 0,
        delta_y: int = 0,
    ) -> InputDispatchResult:
        if delta_x == 0 and delta_y == 0:
            raise WispHandError(
                "invalid_parameters",
                "scroll requires a non-zero delta",
                {"delta_x": delta_x, "delta_y": delta_y},
            )

        policy_action: dict[str, JSONValue] = {
            "kind": "pointer.scroll",
            "scope_position": {"x": x, "y": y},
            "delta_x": delta_x,
            "delta_y": delta_y,
        }
        return self._run_input_action(
            "hand.pointer.scroll",
            session_id=session_id,
            policy_action=policy_action,
            prepare=lambda session: self._prepare_pointer_target(
                session=session,
                kind="pointer.scroll",
                scope_x=x,
                scope_y=y,
                extra={"delta_x": delta_x, "delta_y": delta_y},
            ),
            dispatch=lambda prepared: self._input_backend.scroll_pointer(
                x=int(prepared["absolute_position"]["x"]),  # type: ignore[index]
                y=int(prepared["absolute_position"]["y"]),  # type: ignore[index]
                delta_x=delta_x,
                delta_y=delta_y,
                desktop_bounds=prepared["desktop_bounds"],  # type: ignore[arg-type]
            ),
        )

    def keyboard_type(self, *, session_id: str, text: str) -> InputDispatchResult:
        if not text:
            raise WispHandError("invalid_parameters", "text must not be empty")

        policy_action: dict[str, JSONValue] = {
            "kind": "keyboard.type",
            "text": text,
            "text_length": len(text),
        }
        return self._run_input_action(
            "hand.keyboard.type",
            session_id=session_id,
            policy_action=policy_action,
            prepare=lambda session: {
                "session_id": session.session_id,
                "scope": session.scope,
                "action": policy_action,
            },
            dispatch=lambda prepared: self._input_backend.type_text(
                text=str(prepared["action"]["text"]),  # type: ignore[index]
            ),
        )

    def keyboard_press(self, *, session_id: str, keys: list[str]) -> InputDispatchResult:
        normalized_keys = [normalize_key_name(key) for key in keys]
        if not normalized_keys:
            raise WispHandError("invalid_parameters", "keys must include at least one key")

        policy_action: dict[str, JSONValue] = {
            "kind": "keyboard.press",
            "keys": normalized_keys,
        }
        return self._run_input_action(
            "hand.keyboard.press",
            session_id=session_id,
            policy_action=policy_action,
            prepare=lambda session: {
                "session_id": session.session_id,
                "scope": session.scope,
                "action": policy_action,
            },
            dispatch=lambda prepared: self._input_backend.press_keys(
                keys=[str(key) for key in prepared["action"]["keys"]],  # type: ignore[index]
            ),
        )

    def trigger_emergency_stop(self, *, reason: str = "manual") -> None:
        self._input_policy.trigger_emergency_stop(reason=reason)

    def clear_emergency_stop(self) -> None:
        self._input_policy.clear_emergency_stop()

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
                    status=self._audit_status_for_error(exc.code),
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

    def _run_input_action(
        self,
        tool_name: str,
        *,
        session_id: str,
        policy_action: dict[str, JSONValue],
        prepare: Callable[[SessionRecord], dict[str, object]],
        dispatch: Callable[[dict[str, object]], None],
    ) -> InputDispatchResult:
        def action() -> InputDispatchResult:
            session = self._session_store.get_session(session_id)
            if not session.armed:
                raise WispHandError(
                    "session_not_armed",
                    "Session must be armed before dispatching input",
                    {"session_id": session_id},
                )

            self._input_policy.evaluate(
                session_id=session_id,
                tool_name=tool_name,
                action=policy_action,
            )
            prepared = prepare(session)
            dispatch_state = "dry_run" if session.dry_run else "executed"
            if not session.dry_run:
                dispatch(prepared)
            result_action = prepared["action"]
            if not isinstance(result_action, dict):
                raise WispHandError("internal_error", "prepared input action is invalid", {})
            return {
                "session_id": session_id,
                "scope": session.scope,
                "dispatch_state": dispatch_state,
                "action": result_action,  # type: ignore[typeddict-item]
            }

        return self._run_tool(tool_name, action=action, session_id=session_id)

    def _prepare_pointer_target(
        self,
        *,
        session: SessionRecord,
        kind: str,
        scope_x: int,
        scope_y: int,
        extra: dict[str, JSONValue] | None = None,
    ) -> dict[str, JSONValue]:
        topology = self._hyprland.get_topology()
        bounds = self._hyprland.scope_bounds(session.scope, topology)
        absolute = self._resolve_scope_point(
            bounds=bounds,
            scope_x=scope_x,
            scope_y=scope_y,
            point_name="target",
        )
        action: dict[str, JSONValue] = {
            "kind": kind,
            "scope_position": {"x": scope_x, "y": scope_y},
            "absolute_position": absolute,
        }
        if extra:
            action.update(extra)
        return {
            "session_id": session.session_id,
            "scope": session.scope,
            "action": action,
            "absolute_position": absolute,
            "desktop_bounds": desktop_bounds(topology),
        }

    def _prepare_pointer_drag(
        self,
        *,
        session: SessionRecord,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        button: PointerButton,
    ) -> dict[str, JSONValue]:
        topology = self._hyprland.get_topology()
        bounds = self._hyprland.scope_bounds(session.scope, topology)
        absolute_start = self._resolve_scope_point(
            bounds=bounds,
            scope_x=start_x,
            scope_y=start_y,
            point_name="start",
        )
        absolute_end = self._resolve_scope_point(
            bounds=bounds,
            scope_x=end_x,
            scope_y=end_y,
            point_name="end",
        )
        return {
            "session_id": session.session_id,
            "scope": session.scope,
            "action": {
                "kind": "pointer.drag",
                "button": button,
                "scope_start": {"x": start_x, "y": start_y},
                "scope_end": {"x": end_x, "y": end_y},
                "absolute_start": absolute_start,
                "absolute_end": absolute_end,
            },
            "absolute_start": absolute_start,
            "absolute_end": absolute_end,
            "desktop_bounds": desktop_bounds(topology),
        }

    @staticmethod
    def _resolve_scope_point(
        *,
        bounds: dict[str, int],
        scope_x: int,
        scope_y: int,
        point_name: str,
    ) -> dict[str, int]:
        if scope_x < 0 or scope_y < 0 or scope_x >= bounds["width"] or scope_y >= bounds["height"]:
            raise WispHandError(
                "scope_violation",
                f"{point_name} coordinates exceed the session scope",
                {
                    "point": point_name,
                    "scope_x": scope_x,
                    "scope_y": scope_y,
                    "bounds": bounds,
                },
            )
        return {
            "x": bounds["x"] + scope_x,
            "y": bounds["y"] + scope_y,
        }

    @staticmethod
    def _normalize_button(button: PointerButton) -> PointerButton:
        if button not in {"left", "middle", "right"}:
            raise WispHandError("invalid_parameters", "Unsupported pointer button", {"button": button})
        return button

    @staticmethod
    def _audit_status_for_error(code: str) -> str:
        if code in {"policy_denied", "scope_violation", "session_not_armed"}:
            return "denied"
        return "error"

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
