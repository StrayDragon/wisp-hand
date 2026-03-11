from __future__ import annotations

from dataclasses import dataclass

import pytest

from wisp_hand.coordinates.models import Bounds, CoordinateMap
from wisp_hand.input.policy import InputPolicy
from wisp_hand.input.service import InputService
from wisp_hand.session.store import SessionStore
from wisp_hand.shared.errors import WispHandError

REGION_SCOPE = {
    "type": "region",
    "target": {"x": 100, "y": 200, "width": 50, "height": 40},
    "coordinate_space": {"origin": "scope", "units": "px", "relative_to": "region"},
    "constraints": {"input_relative": True},
}


@dataclass
class FakeInputBackend:
    calls: list[tuple[str, dict[str, object]]]

    def __init__(self) -> None:
        self.calls = []

    def move_pointer(self, *, x: int, y: int, desktop_bounds: dict[str, int]) -> None:
        self.calls.append(("move", {"x": x, "y": y, "desktop_bounds": desktop_bounds}))

    def click_pointer(self, *, x: int, y: int, button: str, desktop_bounds: dict[str, int]) -> None:
        self.calls.append(
            ("click", {"x": x, "y": y, "button": button, "desktop_bounds": desktop_bounds})
        )

    def drag_pointer(
        self,
        *,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        button: str,
        desktop_bounds: dict[str, int],
    ) -> None:
        self.calls.append(
            (
                "drag",
                {
                    "start_x": start_x,
                    "start_y": start_y,
                    "end_x": end_x,
                    "end_y": end_y,
                    "button": button,
                    "desktop_bounds": desktop_bounds,
                },
            )
        )

    def scroll_pointer(
        self,
        *,
        x: int,
        y: int,
        delta_x: int,
        delta_y: int,
        desktop_bounds: dict[str, int],
    ) -> None:
        self.calls.append(
            (
                "scroll",
                {
                    "x": x,
                    "y": y,
                    "delta_x": delta_x,
                    "delta_y": delta_y,
                    "desktop_bounds": desktop_bounds,
                },
            )
        )

    def type_text(self, *, text: str) -> None:
        self.calls.append(("type", {"text": text}))

    def press_keys(self, *, keys: list[str]) -> None:
        self.calls.append(("press", {"keys": list(keys)}))


class FakeDesktopService:
    def __init__(self) -> None:
        self.coordinate_map = CoordinateMap(
            backend="hyprctl-infer",
            confidence=1.0,
            topology_fingerprint="fixture",
            cached=False,
            desktop_layout_bounds=Bounds(x=0, y=0, width=1920, height=1080),
            monitors=[],
        )

    def resolve_topology_context(self) -> tuple[dict[str, object], CoordinateMap]:
        return {"monitors": []}, self.coordinate_map

    def scope_bounds(self, scope, topology, *, coordinate_map) -> dict[str, int]:
        return {"x": 100, "y": 200, "width": 50, "height": 40}


def build_input_service() -> tuple[InputService, SessionStore, FakeInputBackend]:
    store = SessionStore(default_ttl_seconds=30, max_ttl_seconds=120)
    backend = FakeInputBackend()
    service = InputService(
        session_store=store,
        desktop_service=FakeDesktopService(),
        input_backend=backend,
        input_policy=InputPolicy(
            max_actions_per_window=8,
            rate_limit_window_seconds=1.0,
            dangerous_shortcuts=["ctrl+alt+delete"],
        ),
    )
    return service, store, backend


def test_input_service_pointer_click_maps_scope_coordinates_to_absolute() -> None:
    service, store, backend = build_input_service()
    session = store.create_session(
        scope=REGION_SCOPE,
        armed=True,
        dry_run=False,
        ttl_seconds=30,
    )

    result = service.pointer_click(session_id=session.session_id, x=5, y=6, button="right")

    assert result["dispatch_state"] == "executed"
    assert result["action"] == {
        "kind": "pointer.click",
        "scope_position": {"x": 5, "y": 6},
        "absolute_position": {"x": 105, "y": 206},
        "button": "right",
    }
    assert backend.calls == [
        (
            "click",
            {
                "x": 105,
                "y": 206,
                "button": "right",
                "desktop_bounds": {"x": 0, "y": 0, "width": 1920, "height": 1080},
            },
        )
    ]


def test_input_service_rejects_unarmed_sessions() -> None:
    service, store, _ = build_input_service()
    session = store.create_session(
        scope=REGION_SCOPE,
        armed=False,
        dry_run=False,
        ttl_seconds=30,
    )

    with pytest.raises(WispHandError) as exc_info:
        service.pointer_move(session_id=session.session_id, x=1, y=2)
    assert exc_info.value.code == "session_not_armed"


def test_input_service_rejects_zero_scroll_delta() -> None:
    service, store, _ = build_input_service()
    session = store.create_session(
        scope=REGION_SCOPE,
        armed=True,
        dry_run=False,
        ttl_seconds=30,
    )

    with pytest.raises(WispHandError) as exc_info:
        service.pointer_scroll(session_id=session.session_id, x=1, y=2, delta_x=0, delta_y=0)
    assert exc_info.value.code == "invalid_parameters"
