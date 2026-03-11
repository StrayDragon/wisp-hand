from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from time import perf_counter, sleep
from uuid import uuid4

from structlog.contextvars import bind_contextvars, unbind_contextvars

from wisp_hand.desktop.scope import normalize_scope
from wisp_hand.infra.audit import AuditLogger, AuditRecord
from wisp_hand.batch.models import BatchRunResult, WaitResult
from wisp_hand.batch.service import BatchService
from wisp_hand.capabilities.models import CapabilityResult
from wisp_hand.capabilities.service import CapabilitiesService, DependencyProbe
from wisp_hand.capture import (
    CaptureArtifactStore,
    CaptureDiffEngine,
    CaptureEngine,
    CaptureTarget,
    capture_metadata_uri,
    capture_png_uri,
)
from wisp_hand.capture.models import CaptureDiffResult
from wisp_hand.capture.service import CaptureService
from wisp_hand.desktop.hyprland_adapter import HyprlandAdapter
from wisp_hand.desktop.service import DesktopService
from wisp_hand.infra.command import CommandRunner
from wisp_hand.infra.config import RuntimeConfig, load_runtime_config
from wisp_hand.coordinates.models import CoordinateMap
from wisp_hand.coordinates.service import CoordinateService
from wisp_hand.infra.discovery import build_discovery_report
from wisp_hand.infra.observability import get_logger, init_logging
from wisp_hand.input.backend import InputBackend, WaylandInputBackend
from wisp_hand.input.models import InputDispatchResult, PointerButton
from wisp_hand.input.policy import InputPolicy
from wisp_hand.input.service import InputService
from wisp_hand.session.models import ScopeEnvelope, ScopeType, SessionCloseResult, SessionOpenResult
from wisp_hand.session.service import SessionService
from wisp_hand.session.store import SessionStore
from wisp_hand.shared.errors import WispHandError, internal_error
from wisp_hand.shared.types import JSONValue
from wisp_hand.vision.models import VisionDescribeResult, VisionLocateResult
from wisp_hand.vision.provider import OllamaTransport, OllamaVisionProvider, PreparedVisionImage
from wisp_hand.vision.service import VisionService

_AUDIT_CONTEXT: ContextVar[dict[str, JSONValue] | None] = ContextVar("_AUDIT_CONTEXT", default=None)


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
        capture_diff_engine: CaptureDiffEngine | None = None,
        input_backend: InputBackend | None = None,
        input_policy: InputPolicy | None = None,
        vision_provider: OllamaVisionProvider | None = None,
        ollama_transport: OllamaTransport | None = None,
        now_provider: Callable[[], datetime] | None = None,
        monotonic_provider: Callable[[], float] | None = None,
        sleep_provider: Callable[[float], None] | None = None,
    ) -> None:
        self.config = config
        try:
            init_logging(config)
        except Exception:  # pragma: no cover - logging must never break runtime
            pass
        self._logger = get_logger("runtime")
        self._tool_lock = RLock()
        self.runtime_instance_id = str(uuid4())
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self.started_at = self._now_provider().isoformat()
        self._sleep_provider = sleep_provider or sleep
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
        self._startup_discovery = build_discovery_report(
            config=self.config,
            dependency_probe=self._dependency_probe,
            runtime_instance_id=self.runtime_instance_id,
            started_at=self.started_at,
            include_path_checks=True,
        )
        self._hyprland = hyprland_adapter or HyprlandAdapter(runner=self._command_runner)
        self._coordinates = CoordinateService(
            config=self.config.coordinates,
            state_dir=self.config.paths.state_dir,
            runner=self._command_runner,
        )
        self._capture_store = CaptureArtifactStore(base_dir=config.paths.capture_dir)
        try:
            summary = self._capture_store.enforce_retention(
                max_age_seconds=config.retention.captures.max_age_seconds,
                max_total_bytes=config.retention.captures.max_total_bytes,
                now=self._now_provider(),
            )
            if summary.get("removed_count"):
                self._safe_log("capture.retention", **summary)
        except Exception:  # pragma: no cover - retention must never break runtime
            pass
        self._capture_engine = capture_engine or CaptureEngine(
            artifact_store=self._capture_store,
            runner=self._command_runner,
            now_provider=self._now_provider,
        )
        self._capture_diff_engine = capture_diff_engine or CaptureDiffEngine(
            artifact_store=self._capture_store,
        )
        self._input_backend = input_backend or WaylandInputBackend(runner=self._command_runner)
        self._input_policy = input_policy or InputPolicy(
            max_actions_per_window=config.safety.max_actions_per_window,
            rate_limit_window_seconds=config.safety.rate_limit_window_seconds,
            dangerous_shortcuts=config.safety.dangerous_shortcuts,
            monotonic_provider=monotonic_provider,
        )
        self._vision_provider = vision_provider or (
            OllamaVisionProvider(
                base_url=config.vision.base_url,
                model=config.vision.model or "",
                timeout_seconds=config.vision.timeout_seconds,
                max_tokens=config.vision.max_tokens,
                max_concurrency=config.vision.max_concurrency,
                transport=ollama_transport,
            )
            if config.vision.mode == "assist"
            else None
            )
        self._audit_logger = audit_logger or AuditLogger(
            audit_file=config.paths.audit_file,
            allow_sensitive=config.logging.allow_sensitive,
            max_bytes=config.retention.audit.max_bytes,
            backup_count=config.retention.audit.backup_count,
        )
        self._capabilities_service = CapabilitiesService(startup_discovery=self._startup_discovery)
        self._session_service = SessionService(
            session_store=self._session_store,
            default_armed=config.safety.default_armed,
            default_dry_run=config.safety.default_dry_run,
            runtime_instance_id=self.runtime_instance_id,
            started_at=self.started_at,
            now_provider=self._now_provider,
        )
        self._desktop_service = DesktopService(
            session_store=self._session_store,
            hyprland=self._hyprland,
            coordinates=self._coordinates,
            on_coordinates_resolved=self._handle_coordinate_resolution,
        )
        self._capture_service = CaptureService(
            config=self.config,
            session_store=self._session_store,
            desktop_service=self._desktop_service,
            capture_store=self._capture_store,
            capture_engine=self._capture_engine,
            capture_diff_engine=self._capture_diff_engine,
            runtime_instance_id=self.runtime_instance_id,
            started_at=self.started_at,
            now_provider=self._now_provider,
            log_callback=lambda event, fields: self._safe_log(event, **fields),
        )
        self._input_service = InputService(
            session_store=self._session_store,
            desktop_service=self._desktop_service,
            input_backend=self._input_backend,
            input_policy=self._input_policy,
        )
        self._vision_service = VisionService(
            config=self.config,
            capture_store=self._capture_store,
            vision_provider=self._vision_provider,
        )
        self._batch_service = BatchService(
            session_store=self._session_store,
            pointer_move=self.pointer_move,
            pointer_click=self.pointer_click,
            pointer_drag=self.pointer_drag,
            pointer_scroll=self.pointer_scroll,
            keyboard_type=self.keyboard_type,
            keyboard_press=self.keyboard_press,
            wait=self.wait,
            capture_screen=self.capture_screen,
        )
        self._safe_log(
            "runtime.init",
            transport=self.config.server.transport,
            config_path=str(self.config.config_path),
            runtime_instance_id=self.runtime_instance_id,
        )

    @classmethod
    def from_config_path(cls, config_path: str | None = None) -> "WispHandRuntime":
        path = None if config_path is None else Path(config_path)
        return cls(config=load_runtime_config(path))

    def capabilities(self) -> CapabilityResult:
        result = self._run_tool("wisp_hand.capabilities", action=self._capabilities_service.capabilities)
        self._safe_log(
            "dependencies.probe",
            status=result.get("status"),
            runtime_instance_id=self.runtime_instance_id,
            hyprland_detected=result["hyprland_detected"],
            capture_available=result["capture_available"],
            input_available=result["input_available"],
            vision_available=result["vision_available"],
            missing_binaries=result["missing_binaries"],
            missing_optional=result.get("missing_optional"),
        )
        return result

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
        result = self._run_tool(
            "wisp_hand.session.open",
            action=lambda: self._session_service.open_session(
                scope_type=scope_type,
                scope_target=scope_target,
                armed=armed,
                dry_run=dry_run,
                ttl_seconds=ttl_seconds,
            ),
            scope=requested_scope,
        )
        self._safe_log(
            "session.opened",
            session_id=result["session_id"],
            scope=result["scope"],
            armed=result["armed"],
            dry_run=result["dry_run"],
            expires_at=result["expires_at"],
        )
        return result

    def close_session(self, *, session_id: str) -> SessionCloseResult:
        result = self._run_tool(
            "wisp_hand.session.close",
            action=lambda: self._session_service.close_session(session_id=session_id),
            session_id=session_id,
        )
        self._safe_log(
            "session.closed",
            session_id=result["session_id"],
            closed_at=result["closed_at"],
        )
        return result

    def get_topology(self, *, detail: str = "summary") -> JSONValue:
        return self._run_tool(
            "wisp_hand.desktop.get_topology",
            action=lambda: self._desktop_service.get_topology(detail=detail),
        )

    def get_active_window(self) -> JSONValue:
        return self._run_tool(
            "wisp_hand.desktop.get_active_window",
            action=self._desktop_service.get_active_window,
        )

    def get_monitors(self) -> JSONValue:
        return self._run_tool(
            "wisp_hand.desktop.get_monitors",
            action=self._desktop_service.get_monitors,
        )

    def list_windows(self, *, limit: int = 50) -> JSONValue:
        return self._run_tool(
            "wisp_hand.desktop.list_windows",
            action=lambda: self._desktop_service.list_windows(limit=limit),
        )

    def get_cursor_position(self, *, session_id: str) -> JSONValue:
        return self._run_tool(
            "wisp_hand.cursor.get_position",
            action=lambda: self._desktop_service.get_cursor_position(session_id=session_id),
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
        result = self._run_tool(
            "wisp_hand.capture.screen",
            action=lambda: self._capture_service.capture_screen(
                session_id=session_id,
                target=target,
                inline=inline,
                with_cursor=with_cursor,
                downscale=downscale,
            ),
            session_id=session_id,
        )
        if isinstance(result, dict):
            capture_id = result.get("capture_id")
            if isinstance(capture_id, str) and capture_id:
                result["image_uri"] = capture_png_uri(capture_id)
                result["metadata_uri"] = capture_metadata_uri(capture_id)

            self._safe_log(
                "capture.screen",
                capture_id=result.get("capture_id"),
                target=result.get("target"),
                width=result.get("width"),
                height=result.get("height"),
                downscale=result.get("downscale"),
                inline=inline,
                with_cursor=with_cursor,
            )
        return result

    def wait(self, *, session_id: str, duration_ms: int) -> WaitResult:
        if duration_ms < 0:
            raise WispHandError(
                "invalid_parameters",
                "duration_ms must be greater than or equal to zero",
                {"duration_ms": duration_ms},
            )

        def action() -> WaitResult:
            session = self._session_store.get_session(session_id)
            started = perf_counter()
            self._sleep_provider(duration_ms / 1000)
            return {
                "session_id": session.session_id,
                "duration_ms": duration_ms,
                "elapsed_ms": self._elapsed_ms(started),
            }

        return self._run_tool(
            "wisp_hand.wait",
            action=action,
            session_id=session_id,
        )

    def capture_diff(self, *, left_capture_id: str, right_capture_id: str) -> CaptureDiffResult:
        return self._run_tool(
            "wisp_hand.capture.diff",
            action=lambda: self._capture_service.capture_diff(
                left_capture_id=left_capture_id,
                right_capture_id=right_capture_id,
            ),
        )

    def batch_run(
        self,
        *,
        session_id: str,
        steps: list[dict[str, JSONValue]],
        stop_on_error: bool = True,
        return_mode: str = "summary",
    ) -> BatchRunResult:
        return self._run_tool(
            "wisp_hand.batch.run",
            action=lambda: self._batch_service.batch_run(
                session_id=session_id,
                steps=steps,
                stop_on_error=stop_on_error,
                return_mode=return_mode,
                audit_context_factory=self._audit_context,
            ),
            session_id=session_id,
        )

    def vision_describe(
        self,
        *,
        capture_id: str | None = None,
        inline_image: str | None = None,
        prompt: str | None = None,
    ) -> VisionDescribeResult:
        image, provider = self._vision_service.prepare_request(capture_id=capture_id, inline_image=inline_image)

        with self._vision_audit_context(image=image, provider=provider):
            result = self._run_tool(
                "wisp_hand.vision.describe",
                action=lambda: self._vision_service.vision_describe(
                    image=image,
                    provider=provider,
                    prompt=prompt,
                ),
            )
            self._safe_log(
                "vision.describe",
                latency_ms=result["latency_ms"],
                input_source=result["input_source"],
                capture_id=result["capture_id"],
            )
            return result

    def vision_locate(
        self,
        *,
        capture_id: str,
        target: str,
        limit: int = 3,
        space: str = "scope",
    ) -> VisionLocateResult:
        image, provider = self._vision_service.prepare_request(capture_id=capture_id, inline_image=None)

        with self._vision_audit_context(image=image, provider=provider):
            result = self._run_tool(
                "wisp_hand.vision.locate",
                action=lambda: self._vision_service.vision_locate(
                    image=image,
                    provider=provider,
                    capture_id=capture_id,
                    target=target,
                    limit=limit,
                    space=space,
                ),
            )
            self._safe_log(
                "vision.locate",
                latency_ms=result["latency_ms"],
                input_source=result["input_source"],
                capture_id=result["capture_id"],
                target=result["target"],
                candidates_scope=len(result.get("candidates_scope") or []),
                candidates_image=len(result.get("candidates_image") or []),
            )
            return result

    def pointer_move(self, *, session_id: str, x: int, y: int) -> InputDispatchResult:
        result = self._run_tool(
            "wisp_hand.pointer.move",
            session_id=session_id,
            action=lambda: self._input_service.pointer_move(session_id=session_id, x=x, y=y),
        )
        self._safe_log(
            "input.dispatch",
            tool_name="wisp_hand.pointer.move",
            session_id=session_id,
            dispatch_state=result["dispatch_state"],
            action=result["action"],
        )
        return result

    def pointer_click(
        self,
        *,
        session_id: str,
        x: int,
        y: int,
        button: PointerButton = "left",
    ) -> InputDispatchResult:
        result = self._run_tool(
            "wisp_hand.pointer.click",
            session_id=session_id,
            action=lambda: self._input_service.pointer_click(session_id=session_id, x=x, y=y, button=button),
        )
        self._safe_log(
            "input.dispatch",
            tool_name="wisp_hand.pointer.click",
            session_id=session_id,
            dispatch_state=result["dispatch_state"],
            action=result["action"],
        )
        return result

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
        result = self._run_tool(
            "wisp_hand.pointer.drag",
            session_id=session_id,
            action=lambda: self._input_service.pointer_drag(
                session_id=session_id,
                start_x=start_x,
                start_y=start_y,
                end_x=end_x,
                end_y=end_y,
                button=button,
            ),
        )
        self._safe_log(
            "input.dispatch",
            tool_name="wisp_hand.pointer.drag",
            session_id=session_id,
            dispatch_state=result["dispatch_state"],
            action=result["action"],
        )
        return result

    def pointer_scroll(
        self,
        *,
        session_id: str,
        x: int,
        y: int,
        delta_x: int = 0,
        delta_y: int = 0,
    ) -> InputDispatchResult:
        result = self._run_tool(
            "wisp_hand.pointer.scroll",
            session_id=session_id,
            action=lambda: self._input_service.pointer_scroll(
                session_id=session_id,
                x=x,
                y=y,
                delta_x=delta_x,
                delta_y=delta_y,
            ),
        )
        self._safe_log(
            "input.dispatch",
            tool_name="wisp_hand.pointer.scroll",
            session_id=session_id,
            dispatch_state=result["dispatch_state"],
            action=result["action"],
        )
        return result

    def keyboard_type(self, *, session_id: str, text: str) -> InputDispatchResult:
        result = self._run_tool(
            "wisp_hand.keyboard.type",
            session_id=session_id,
            action=lambda: self._input_service.keyboard_type(session_id=session_id, text=text),
        )
        self._safe_log(
            "input.dispatch",
            tool_name="wisp_hand.keyboard.type",
            session_id=session_id,
            dispatch_state=result["dispatch_state"],
            action=result["action"],
        )
        return result

    def keyboard_press(self, *, session_id: str, keys: list[str]) -> InputDispatchResult:
        result = self._run_tool(
            "wisp_hand.keyboard.press",
            session_id=session_id,
            action=lambda: self._input_service.keyboard_press(session_id=session_id, keys=keys),
        )
        self._safe_log(
            "input.dispatch",
            tool_name="wisp_hand.keyboard.press",
            session_id=session_id,
            dispatch_state=result["dispatch_state"],
            action=result["action"],
        )
        return result

    def trigger_emergency_stop(self, *, reason: str = "manual") -> None:
        self._input_service.trigger_emergency_stop(reason=reason)

    def clear_emergency_stop(self) -> None:
        self._input_service.clear_emergency_stop()

    @contextmanager
    def _vision_audit_context(
        self,
        *,
        image: PreparedVisionImage,
        provider: OllamaVisionProvider,
    ):
        with self._audit_context(
            {
                "input_source": image.input_source,
                "provider": provider.provider_name,
                "model": provider.model,
                "capture_id": image.capture_id,
                "image_width": image.width,
                "image_height": image.height,
                "processed_width": image.processed_width,
                "processed_height": image.processed_height,
            }
        ):
            yield

    def _handle_coordinate_resolution(self, coordinate_map: CoordinateMap) -> None:
        self._safe_log(
            "coordinates.resolved",
            backend=coordinate_map.backend,
            confidence=coordinate_map.confidence,
            cached=coordinate_map.cached,
            topology_fingerprint=coordinate_map.topology_fingerprint,
        )

    @contextmanager
    def _audit_context(self, values: dict[str, JSONValue]):
        current = _AUDIT_CONTEXT.get() or {}
        token: Token[dict[str, JSONValue] | None] = _AUDIT_CONTEXT.set({**current, **values})
        restore: dict[str, JSONValue] = {key: current[key] for key in values if key in current}
        drop = [key for key in values if key not in current]
        try:
            try:
                bind_contextvars(**values)
            except Exception:  # pragma: no cover - defensive
                pass
            yield
        finally:
            try:
                if drop:
                    unbind_contextvars(*drop)
                if restore:
                    bind_contextvars(**restore)
            except Exception:  # pragma: no cover - defensive
                pass
            _AUDIT_CONTEXT.reset(token)

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
            # Tools may be executed from multiple threads when using MCP tasks.
            # Serialize access to internal runtime state to keep session/audit behavior stable.
            with self._tool_lock:
                result = action()
        except WispHandError as exc:
            exc.details.setdefault("runtime_instance_id", self.runtime_instance_id)
            exc.details.setdefault("started_at", self.started_at)
            status = self._audit_status_for_error(exc.code)
            latency_ms = self._elapsed_ms(started)
            error = exc.to_payload()
            self._audit_logger.record(
                self._build_audit_record(
                    tool_name=tool_name,
                    status=status,
                    latency_ms=latency_ms,
                    session_id=session_id,
                    scope=scope,
                    error=error,
                )
            )
            self._safe_tool_log(
                tool_name=tool_name,
                status=status,
                latency_ms=latency_ms,
                session_id=session_id,
                scope=scope,
                error=error,
            )
            raise
        except Exception as exc:  # pragma: no cover - defensive wrapper
            error = internal_error(str(exc))
            error.details.setdefault("runtime_instance_id", self.runtime_instance_id)
            error.details.setdefault("started_at", self.started_at)
            latency_ms = self._elapsed_ms(started)
            payload = error.to_payload()
            self._audit_logger.record(
                self._build_audit_record(
                    tool_name=tool_name,
                    status="error",
                    latency_ms=latency_ms,
                    session_id=session_id,
                    scope=scope,
                    error=payload,
                )
            )
            self._safe_tool_log(
                tool_name=tool_name,
                status="error",
                latency_ms=latency_ms,
                session_id=session_id,
                scope=scope,
                error=payload,
            )
            raise error from exc

        payload_scope = scope
        payload_session_id = session_id
        if isinstance(result, dict):
            payload_scope = result.get("scope", payload_scope)  # type: ignore[assignment]
            payload_session_id = result.get("session_id", payload_session_id)  # type: ignore[assignment]

        latency_ms = self._elapsed_ms(started)
        self._audit_logger.record(
            self._build_audit_record(
                tool_name=tool_name,
                status="ok",
                latency_ms=latency_ms,
                session_id=payload_session_id,
                scope=payload_scope,
                result=result,
            )
        )
        self._safe_tool_log(
            tool_name=tool_name,
            status="ok",
            latency_ms=latency_ms,
            session_id=payload_session_id,
            scope=payload_scope,
            error=None,
        )
        return result


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
            "runtime_instance_id": self.runtime_instance_id,  # type: ignore[typeddict-item]
            "started_at": self.started_at,  # type: ignore[typeddict-item]
        }
        audit_context = _AUDIT_CONTEXT.get()
        if audit_context is not None:
            for key, value in audit_context.items():
                payload[key] = value  # type: ignore[typeddict-item]
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

    def _safe_log(self, event: str, **fields: JSONValue) -> None:
        try:
            self._logger.info(event, **fields)
        except Exception:  # pragma: no cover - logging must be best-effort
            return

    def _safe_tool_log(
        self,
        *,
        tool_name: str,
        status: str,
        latency_ms: int,
        session_id: str | None,
        scope: ScopeEnvelope | None,
        error: dict[str, JSONValue] | None,
    ) -> None:
        event = f"tool.call.{status}"
        payload: dict[str, JSONValue] = {
            "tool_name": tool_name,
            "status": status,
            "latency_ms": latency_ms,
        }
        if session_id is not None:
            payload["session_id"] = session_id
        if scope is not None:
            payload["scope"] = scope
        if error is not None:
            payload["error"] = error

        try:
            if status == "denied":
                self._logger.warning(event, **payload)
            elif status == "error":
                self._logger.error(event, **payload)
            else:
                self._logger.info(event, **payload)
        except Exception:  # pragma: no cover - logging must be best-effort
            return
