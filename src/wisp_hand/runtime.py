from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter, sleep
from uuid import uuid4

from structlog.contextvars import bind_contextvars, unbind_contextvars

from wisp_hand.audit import AuditLogger
from wisp_hand.capabilities import DependencyProbe
from wisp_hand.capture import CaptureArtifactStore, CaptureDiffEngine, CaptureEngine, CaptureTarget
from wisp_hand.command import CommandRunner
from wisp_hand.config import RuntimeConfig, load_runtime_config
from wisp_hand.errors import WispHandError, internal_error
from wisp_hand.hyprland import HyprlandAdapter, desktop_bounds
from wisp_hand.input_backend import InputBackend, WaylandInputBackend
from wisp_hand.models import (
    AuditRecord,
    BatchRunResult,
    BatchStepResult,
    CapabilityResult,
    CaptureDiffResult,
    InputDispatchResult,
    JSONValue,
    PointerButton,
    ScopeEnvelope,
    ScopeType,
    SessionCloseResult,
    SessionOpenResult,
    SessionRecord,
    VisionDescribeResult,
    VisionLocateResult,
    WaitResult,
)
from wisp_hand.policy import InputPolicy, normalize_key_name
from wisp_hand.scope import normalize_scope
from wisp_hand.session import SessionStore
from wisp_hand.vision import (
    OllamaTransport,
    OllamaVisionProvider,
    PreparedVisionImage,
    prepare_capture_image,
    prepare_inline_image,
    scale_candidates,
)
from wisp_hand.observability import get_logger, init_logging

_AUDIT_CONTEXT: ContextVar[dict[str, JSONValue] | None] = ContextVar("_AUDIT_CONTEXT", default=None)

IMPLEMENTED_TOOLS = [
    "hand.capabilities",
    "hand.session.open",
    "hand.session.close",
    "hand.desktop.get_topology",
    "hand.cursor.get_position",
    "hand.capture.screen",
    "hand.wait",
    "hand.capture.diff",
    "hand.batch.run",
    "hand.vision.describe",
    "hand.vision.locate",
    "hand.pointer.move",
    "hand.pointer.click",
    "hand.pointer.drag",
    "hand.pointer.scroll",
    "hand.keyboard.type",
    "hand.keyboard.press",
]


@dataclass(frozen=True, slots=True)
class CompiledBatchStep:
    step_type: str
    executor: Callable[[], JSONValue]


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
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
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
        self._hyprland = hyprland_adapter or HyprlandAdapter(runner=self._command_runner)
        self._capture_store = CaptureArtifactStore(base_dir=config.paths.capture_dir)
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
        )
        self._safe_log(
            "runtime.init",
            transport=self.config.server.transport,
            config_path=str(self.config.config_path),
        )

    @classmethod
    def from_config_path(cls, config_path: str | None = None) -> "WispHandRuntime":
        path = None if config_path is None else Path(config_path)
        return cls(config=load_runtime_config(path))

    def capabilities(self) -> CapabilityResult:
        result = self._run_tool(
            "hand.capabilities",
            action=lambda: self._dependency_probe.report(
                config_path=str(self.config.config_path),
                implemented_tools=IMPLEMENTED_TOOLS,
            ),
        )
        result["vision_available"] = (
            self.config.vision.mode == "assist"
            and bool(self.config.vision.model)
            and bool(self.config.vision.base_url)
        )
        self._safe_log(
            "dependencies.probe",
            hyprland_detected=result["hyprland_detected"],
            capture_available=result["capture_available"],
            input_available=result["input_available"],
            vision_available=result["vision_available"],
            missing_binaries=result["missing_binaries"],
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

        result = self._run_tool(
            "hand.session.open",
            action=action,
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
        def action() -> SessionCloseResult:
            record = self._session_store.close_session(session_id)
            return {
                "session_id": record.session_id,
                "closed": True,
                "closed_at": self._now_provider().isoformat(),
            }

        result = self._run_tool(
            "hand.session.close",
            action=action,
            session_id=session_id,
        )
        self._safe_log(
            "session.closed",
            session_id=result["session_id"],
            closed_at=result["closed_at"],
        )
        return result

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

        result = self._run_tool(
            "hand.capture.screen",
            action=action,
            session_id=session_id,
        )
        if isinstance(result, dict):
            self._safe_log(
                "capture.screen",
                capture_id=result.get("capture_id"),
                target=result.get("target"),
                width=result.get("width"),
                height=result.get("height"),
                downscale=result.get("downscale"),
                inline=inline,
                with_cursor=with_cursor,
                path=result.get("path"),
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
            "hand.wait",
            action=action,
            session_id=session_id,
        )

    def capture_diff(self, *, left_capture_id: str, right_capture_id: str) -> CaptureDiffResult:
        return self._run_tool(
            "hand.capture.diff",
            action=lambda: self._capture_diff_engine.diff(
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
    ) -> BatchRunResult:
        def action() -> BatchRunResult:
            session = self._session_store.get_session(session_id)
            compiled_steps = self._compile_batch_steps(session_id=session_id, steps=steps)
            batch_id = str(uuid4())
            step_results: list[BatchStepResult] = []

            for index, compiled in enumerate(compiled_steps):
                with self._audit_context(
                    {
                        "batch_id": batch_id,
                        "parent_tool_name": "hand.batch.run",
                        "step_index": index,
                        "step_type": compiled.step_type,
                    }
                ):
                    try:
                        output = compiled.executor()
                    except WispHandError as exc:
                        step_results.append(
                            {
                                "index": index,
                                "type": compiled.step_type,
                                "status": "error",
                                "error": exc.to_payload(),
                            }
                        )
                        if stop_on_error:
                            step_results.extend(
                                {
                                    "index": skipped_index,
                                    "type": skipped.step_type,
                                    "status": "skipped",
                                }
                                for skipped_index, skipped in enumerate(compiled_steps[index + 1 :], start=index + 1)
                            )
                            break
                    else:
                        step_results.append(
                            {
                                "index": index,
                                "type": compiled.step_type,
                                "status": "ok",
                                "output": output,
                            }
                        )

            return {
                "batch_id": batch_id,
                "session_id": session.session_id,
                "scope": session.scope,
                "stop_on_error": stop_on_error,
                "step_count": len(compiled_steps),
                "steps": step_results,
            }

        return self._run_tool(
            "hand.batch.run",
            action=action,
            session_id=session_id,
        )

    def vision_describe(
        self,
        *,
        capture_id: str | None = None,
        inline_image: str | None = None,
        prompt: str | None = None,
    ) -> VisionDescribeResult:
        image = self._load_vision_image(capture_id=capture_id, inline_image=inline_image)
        provider = self._require_vision_provider()
        describe_prompt = prompt or "Describe the image concisely for an external computer-use agent."

        def action() -> VisionDescribeResult:
            payload = provider.describe(image=image, prompt=describe_prompt)
            return {
                "provider": payload["provider"],
                "model": payload["model"],
                "input_source": image.input_source,
                "capture_id": image.capture_id,
                "image_width": image.width,
                "image_height": image.height,
                "processed_width": image.processed_width,
                "processed_height": image.processed_height,
                "answer": payload["answer"],
                "latency_ms": payload["latency_ms"],
            }

        with self._vision_audit_context(image=image, provider=provider):
            result = self._run_tool("hand.vision.describe", action=action)
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
    ) -> VisionLocateResult:
        if not target:
            raise WispHandError("invalid_parameters", "target must not be empty")
        image = self._load_vision_image(capture_id=capture_id, inline_image=None)
        provider = self._require_vision_provider()

        def action() -> VisionLocateResult:
            payload = provider.locate(image=image, target=target)
            return {
                "provider": payload["provider"],
                "model": payload["model"],
                "input_source": image.input_source,
                "capture_id": capture_id,
                "image_width": image.width,
                "image_height": image.height,
                "processed_width": image.processed_width,
                "processed_height": image.processed_height,
                "target": target,
                "candidates": scale_candidates(
                    candidates=payload["candidates"],
                    from_width=image.processed_width,
                    from_height=image.processed_height,
                    to_width=image.width,
                    to_height=image.height,
                ),
                "latency_ms": payload["latency_ms"],
            }

        with self._vision_audit_context(image=image, provider=provider):
            result = self._run_tool("hand.vision.locate", action=action)
            self._safe_log(
                "vision.locate",
                latency_ms=result["latency_ms"],
                input_source=result["input_source"],
                capture_id=result["capture_id"],
                target=result["target"],
                candidates=len(result["candidates"]),
            )
            return result

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

    def _require_vision_provider(self) -> OllamaVisionProvider:
        if self.config.vision.mode != "assist":
            raise WispHandError(
                "capability_unavailable",
                "Vision mode is disabled",
                {"mode": self.config.vision.mode},
            )
        if self._vision_provider is None or not self.config.vision.model or not self.config.vision.base_url:
            raise WispHandError(
                "capability_unavailable",
                "Vision provider is not configured",
                {"mode": self.config.vision.mode},
            )
        return self._vision_provider

    def _load_vision_image(
        self,
        *,
        capture_id: str | None,
        inline_image: str | None,
    ) -> PreparedVisionImage:
        if (capture_id is None) == (inline_image is None):
            raise WispHandError(
                "invalid_parameters",
                "exactly one of capture_id or inline_image must be provided",
                {},
            )

        if capture_id is not None:
            return prepare_capture_image(
                artifact_store=self._capture_store,
                capture_id=capture_id,
                max_image_edge=self.config.vision.max_image_edge,
            )

        return prepare_inline_image(
            inline_image=str(inline_image),
            max_image_edge=self.config.vision.max_image_edge,
        )

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

    def _compile_batch_steps(
        self,
        *,
        session_id: str,
        steps: list[dict[str, JSONValue]],
    ) -> list[CompiledBatchStep]:
        compiled: list[CompiledBatchStep] = []
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                raise WispHandError(
                    "invalid_parameters",
                    "batch steps must be JSON objects",
                    {"step_index": index},
                )
            compiled.append(self._compile_batch_step(session_id=session_id, step_index=index, step=step))
        return compiled

    def _compile_batch_step(
        self,
        *,
        session_id: str,
        step_index: int,
        step: dict[str, JSONValue],
    ) -> CompiledBatchStep:
        step_type = step.get("type")
        if not isinstance(step_type, str) or not step_type:
            raise WispHandError(
                "invalid_parameters",
                "batch step type must be a non-empty string",
                {"step_index": step_index},
            )

        if step_type == "move":
            x = self._require_step_int(step, "x", step_index=step_index)
            y = self._require_step_int(step, "y", step_index=step_index)
            return CompiledBatchStep(
                step_type=step_type,
                executor=lambda: self.pointer_move(session_id=session_id, x=x, y=y),
            )

        if step_type == "click":
            x = self._require_step_int(step, "x", step_index=step_index)
            y = self._require_step_int(step, "y", step_index=step_index)
            button = self._normalize_button(
                self._optional_step_string(step, "button", step_index=step_index) or "left"
            )
            return CompiledBatchStep(
                step_type=step_type,
                executor=lambda: self.pointer_click(
                    session_id=session_id,
                    x=x,
                    y=y,
                    button=button,
                ),
            )

        if step_type == "drag":
            start_x = self._require_step_int(step, "start_x", step_index=step_index)
            start_y = self._require_step_int(step, "start_y", step_index=step_index)
            end_x = self._require_step_int(step, "end_x", step_index=step_index)
            end_y = self._require_step_int(step, "end_y", step_index=step_index)
            button = self._normalize_button(
                self._optional_step_string(step, "button", step_index=step_index) or "left"
            )
            return CompiledBatchStep(
                step_type=step_type,
                executor=lambda: self.pointer_drag(
                    session_id=session_id,
                    start_x=start_x,
                    start_y=start_y,
                    end_x=end_x,
                    end_y=end_y,
                    button=button,
                ),
            )

        if step_type == "scroll":
            x = self._require_step_int(step, "x", step_index=step_index)
            y = self._require_step_int(step, "y", step_index=step_index)
            delta_x = self._optional_step_int(step, "delta_x", step_index=step_index) or 0
            delta_y = self._optional_step_int(step, "delta_y", step_index=step_index) or 0
            return CompiledBatchStep(
                step_type=step_type,
                executor=lambda: self.pointer_scroll(
                    session_id=session_id,
                    x=x,
                    y=y,
                    delta_x=delta_x,
                    delta_y=delta_y,
                ),
            )

        if step_type == "type":
            text = self._require_step_string(step, "text", step_index=step_index)
            return CompiledBatchStep(
                step_type=step_type,
                executor=lambda: self.keyboard_type(session_id=session_id, text=text),
            )

        if step_type == "press":
            keys = self._require_step_string_list(step, "keys", step_index=step_index)
            return CompiledBatchStep(
                step_type=step_type,
                executor=lambda: self.keyboard_press(session_id=session_id, keys=keys),
            )

        if step_type == "wait":
            duration_ms = self._require_step_int(step, "duration_ms", step_index=step_index)
            return CompiledBatchStep(
                step_type=step_type,
                executor=lambda: self.wait(session_id=session_id, duration_ms=duration_ms),
            )

        if step_type == "capture":
            target = self._optional_step_string(step, "target", step_index=step_index) or "scope"
            inline = self._optional_step_bool(step, "inline", step_index=step_index) or False
            with_cursor = self._optional_step_bool(step, "with_cursor", step_index=step_index) or False
            downscale = self._optional_step_float(step, "downscale", step_index=step_index)
            return CompiledBatchStep(
                step_type=step_type,
                executor=lambda: self.capture_screen(
                    session_id=session_id,
                    target=target,  # type: ignore[arg-type]
                    inline=inline,
                    with_cursor=with_cursor,
                    downscale=downscale,
                ),
            )

        raise WispHandError(
            "invalid_parameters",
            "Unsupported batch step type",
            {"step_index": step_index, "type": step_type},
        )

    @staticmethod
    def _require_step_int(step: dict[str, JSONValue], key: str, *, step_index: int) -> int:
        value = step.get(key)
        if not isinstance(value, int):
            raise WispHandError(
                "invalid_parameters",
                f"batch step field '{key}' must be an integer",
                {"step_index": step_index, "field": key},
            )
        return value

    @staticmethod
    def _optional_step_int(step: dict[str, JSONValue], key: str, *, step_index: int) -> int | None:
        if key not in step or step[key] is None:
            return None
        return WispHandRuntime._require_step_int(step, key, step_index=step_index)

    @staticmethod
    def _require_step_string(step: dict[str, JSONValue], key: str, *, step_index: int) -> str:
        value = step.get(key)
        if not isinstance(value, str) or not value:
            raise WispHandError(
                "invalid_parameters",
                f"batch step field '{key}' must be a non-empty string",
                {"step_index": step_index, "field": key},
            )
        return value

    @staticmethod
    def _optional_step_string(step: dict[str, JSONValue], key: str, *, step_index: int) -> str | None:
        if key not in step or step[key] is None:
            return None
        return WispHandRuntime._require_step_string(step, key, step_index=step_index)

    @staticmethod
    def _optional_step_bool(step: dict[str, JSONValue], key: str, *, step_index: int) -> bool | None:
        value = step.get(key)
        if value is None and key not in step:
            return None
        if not isinstance(value, bool):
            raise WispHandError(
                "invalid_parameters",
                f"batch step field '{key}' must be a boolean",
                {"step_index": step_index, "field": key},
            )
        return value

    @staticmethod
    def _optional_step_float(step: dict[str, JSONValue], key: str, *, step_index: int) -> float | None:
        value = step.get(key)
        if value is None and key not in step:
            return None
        if not isinstance(value, (int, float)):
            raise WispHandError(
                "invalid_parameters",
                f"batch step field '{key}' must be a number",
                {"step_index": step_index, "field": key},
            )
        return float(value)

    @staticmethod
    def _require_step_string_list(step: dict[str, JSONValue], key: str, *, step_index: int) -> list[str]:
        value = step.get(key)
        if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item for item in value):
            raise WispHandError(
                "invalid_parameters",
                f"batch step field '{key}' must be a non-empty string array",
                {"step_index": step_index, "field": key},
            )
        return [item for item in value]

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
            result = action()
        except WispHandError as exc:
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

        result = self._run_tool(tool_name, action=action, session_id=session_id)
        self._safe_log(
            "input.dispatch",
            tool_name=tool_name,
            session_id=session_id,
            dispatch_state=result["dispatch_state"],
            action=result["action"],
        )
        return result

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
