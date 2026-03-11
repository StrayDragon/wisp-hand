from __future__ import annotations

from collections.abc import Callable

from wisp_hand.desktop.service import DesktopService
from wisp_hand.input.backend import InputBackend
from wisp_hand.input.models import InputDispatchResult, PointerButton
from wisp_hand.input.policy import InputPolicy, normalize_key_name
from wisp_hand.session.models import SessionRecord
from wisp_hand.session.store import SessionStore
from wisp_hand.shared.errors import WispHandError
from wisp_hand.shared.types import JSONValue


class InputService:
    def __init__(
        self,
        *,
        session_store: SessionStore,
        desktop_service: DesktopService,
        input_backend: InputBackend,
        input_policy: InputPolicy,
    ) -> None:
        self._session_store = session_store
        self._desktop = desktop_service
        self._input_backend = input_backend
        self._input_policy = input_policy

    def pointer_move(self, *, session_id: str, x: int, y: int) -> InputDispatchResult:
        policy_action: dict[str, JSONValue] = {
            "kind": "pointer.move",
            "scope_position": {"x": x, "y": y},
        }
        return self._run_input_action(
            "wisp_hand.pointer.move",
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
            "wisp_hand.pointer.click",
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
            "wisp_hand.pointer.drag",
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
            "wisp_hand.pointer.scroll",
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
            "wisp_hand.keyboard.type",
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
            "wisp_hand.keyboard.press",
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

    def _run_input_action(
        self,
        tool_name: str,
        *,
        session_id: str,
        policy_action: dict[str, JSONValue],
        prepare: Callable[[SessionRecord], dict[str, object]],
        dispatch: Callable[[dict[str, object]], None],
    ) -> InputDispatchResult:
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

    def _prepare_pointer_target(
        self,
        *,
        session: SessionRecord,
        kind: str,
        scope_x: int,
        scope_y: int,
        extra: dict[str, JSONValue] | None = None,
    ) -> dict[str, JSONValue]:
        topology, coordinate_map = self._desktop.resolve_topology_context()
        bounds = self._desktop.scope_bounds(session.scope, topology, coordinate_map=coordinate_map)
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
            "desktop_bounds": coordinate_map.desktop_layout_bounds.model_dump(),
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
        topology, coordinate_map = self._desktop.resolve_topology_context()
        bounds = self._desktop.scope_bounds(session.scope, topology, coordinate_map=coordinate_map)
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
            "desktop_bounds": coordinate_map.desktop_layout_bounds.model_dump(),
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
