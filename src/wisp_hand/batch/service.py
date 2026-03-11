from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from uuid import uuid4

from wisp_hand.batch.models import BatchRunResult, BatchStepResult
from wisp_hand.input.models import PointerButton
from wisp_hand.session.store import SessionStore
from wisp_hand.shared.errors import WispHandError
from wisp_hand.shared.types import JSONValue


@dataclass(frozen=True, slots=True)
class CompiledBatchStep:
    step_type: str
    executor: Callable[[], JSONValue]


class BatchService:
    def __init__(
        self,
        *,
        session_store: SessionStore,
        pointer_move: Callable[..., JSONValue],
        pointer_click: Callable[..., JSONValue],
        pointer_drag: Callable[..., JSONValue],
        pointer_scroll: Callable[..., JSONValue],
        keyboard_type: Callable[..., JSONValue],
        keyboard_press: Callable[..., JSONValue],
        wait: Callable[..., JSONValue],
        capture_screen: Callable[..., JSONValue],
    ) -> None:
        self._session_store = session_store
        self._pointer_move = pointer_move
        self._pointer_click = pointer_click
        self._pointer_drag = pointer_drag
        self._pointer_scroll = pointer_scroll
        self._keyboard_type = keyboard_type
        self._keyboard_press = keyboard_press
        self._wait = wait
        self._capture_screen = capture_screen

    def batch_run(
        self,
        *,
        session_id: str,
        steps: list[dict[str, JSONValue]],
        stop_on_error: bool = True,
        return_mode: str = "summary",
        audit_context_factory: Callable[[dict[str, JSONValue]], AbstractContextManager[None]],
    ) -> BatchRunResult:
        allowed_modes = {"summary", "full"}
        if not isinstance(return_mode, str) or return_mode not in allowed_modes:
            raise WispHandError(
                "invalid_parameters",
                "return_mode must be one of: summary, full",
                {"return_mode": return_mode, "allowed": sorted(allowed_modes)},
            )

        session = self._session_store.get_session(session_id)
        compiled_steps = self._compile_batch_steps(session_id=session_id, steps=steps)
        batch_id = str(uuid4())
        step_results: list[BatchStepResult] = []

        def summarize_output(step_type: str, output: JSONValue) -> JSONValue | None:
            if step_type == "capture" and isinstance(output, dict):
                capture_id = output.get("capture_id")
                if not isinstance(capture_id, str) or not capture_id:
                    return None
                summary: dict[str, JSONValue] = {"capture_id": capture_id}
                for key in ("image_uri", "metadata_uri"):
                    value = output.get(key)
                    if isinstance(value, str) and value:
                        summary[key] = value
                return summary
            return None

        def summarize_error(payload: dict[str, JSONValue]) -> dict[str, JSONValue]:
            code = payload.get("code")
            message = payload.get("message")
            return {
                "code": str(code) if isinstance(code, str) else "internal_error",
                "message": str(message) if isinstance(message, str) else "Internal server error",
                "details": {},
            }

        for index, compiled in enumerate(compiled_steps):
            with audit_context_factory(
                {
                    "batch_id": batch_id,
                    "parent_tool_name": "wisp_hand.batch.run",
                    "step_index": index,
                    "step_type": compiled.step_type,
                }
            ):
                try:
                    output = compiled.executor()
                except WispHandError as exc:
                    error_payload = exc.to_payload()
                    step_results.append(
                        {
                            "index": index,
                            "type": compiled.step_type,
                            "status": "error",
                            "error": summarize_error(error_payload) if return_mode == "summary" else error_payload,
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
                    step_payload: BatchStepResult = {
                        "index": index,
                        "type": compiled.step_type,
                        "status": "ok",
                    }
                    if return_mode == "full":
                        step_payload["output"] = output
                    else:
                        summarized = summarize_output(compiled.step_type, output)
                        if summarized is not None:
                            step_payload["output"] = summarized
                    step_results.append(step_payload)

        return {
            "batch_id": batch_id,
            "return_mode": return_mode,  # type: ignore[typeddict-item]
            "session_id": session.session_id,
            "scope": session.scope,
            "stop_on_error": stop_on_error,
            "step_count": len(compiled_steps),
            "steps": step_results,
        }

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
                executor=lambda: self._pointer_move(session_id=session_id, x=x, y=y),
            )

        if step_type == "click":
            x = self._require_step_int(step, "x", step_index=step_index)
            y = self._require_step_int(step, "y", step_index=step_index)
            button = self._normalize_button(
                self._optional_step_string(step, "button", step_index=step_index) or "left"
            )
            return CompiledBatchStep(
                step_type=step_type,
                executor=lambda: self._pointer_click(session_id=session_id, x=x, y=y, button=button),
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
                executor=lambda: self._pointer_drag(
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
                executor=lambda: self._pointer_scroll(
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
                executor=lambda: self._keyboard_type(session_id=session_id, text=text),
            )

        if step_type == "press":
            keys = self._require_step_string_list(step, "keys", step_index=step_index)
            return CompiledBatchStep(
                step_type=step_type,
                executor=lambda: self._keyboard_press(session_id=session_id, keys=keys),
            )

        if step_type == "wait":
            duration_ms = self._require_step_int(step, "duration_ms", step_index=step_index)
            return CompiledBatchStep(
                step_type=step_type,
                executor=lambda: self._wait(session_id=session_id, duration_ms=duration_ms),
            )

        if step_type == "capture":
            target = self._optional_step_string(step, "target", step_index=step_index) or "scope"
            inline = self._optional_step_bool(step, "inline", step_index=step_index) or False
            with_cursor = self._optional_step_bool(step, "with_cursor", step_index=step_index) or False
            downscale = self._optional_step_float(step, "downscale", step_index=step_index)
            return CompiledBatchStep(
                step_type=step_type,
                executor=lambda: self._capture_screen(
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
        return BatchService._require_step_int(step, key, step_index=step_index)

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
        return BatchService._require_step_string(step, key, step_index=step_index)

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

    @staticmethod
    def _normalize_button(button: str) -> PointerButton:
        if button not in {"left", "middle", "right"}:
            raise WispHandError("invalid_parameters", "Unsupported pointer button", {"button": button})
        return button  # type: ignore[return-value]
