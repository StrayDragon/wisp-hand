from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from wisp_hand.session.service import SessionService
from wisp_hand.session.store import SessionStore
from wisp_hand.shared.errors import WispHandError


class FakeClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 3, 9, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    def advance(self, *, seconds: int) -> None:
        self.current += timedelta(seconds=seconds)


def build_service(clock: FakeClock) -> tuple[SessionService, SessionStore]:
    store = SessionStore(
        default_ttl_seconds=30,
        max_ttl_seconds=120,
        now_provider=clock.now,
    )
    service = SessionService(
        session_store=store,
        default_armed=True,
        default_dry_run=False,
        runtime_instance_id="runtime-1",
        started_at="2026-03-09T00:00:00+00:00",
        now_provider=clock.now,
    )
    return service, store


def test_session_service_open_uses_defaults_and_normalizes_scope() -> None:
    clock = FakeClock()
    service, store = build_service(clock)

    opened = service.open_session(
        scope_type="region",
        scope_target={"x": 10, "y": 20, "width": 300, "height": 200},
        armed=None,
        dry_run=None,
        ttl_seconds=15,
    )

    assert opened["runtime_instance_id"] == "runtime-1"
    assert opened["started_at"] == "2026-03-09T00:00:00+00:00"
    assert opened["armed"] is True
    assert opened["dry_run"] is False
    assert opened["scope"] == {
        "type": "region",
        "target": {"x": 10, "y": 20, "width": 300, "height": 200},
        "coordinate_space": {"origin": "scope", "units": "px", "relative_to": "region"},
        "constraints": {"input_relative": True},
    }

    record = store.get_session(opened["session_id"])
    assert record.scope == opened["scope"]
    assert opened["expires_at"] == (clock.now() + timedelta(seconds=15)).isoformat()


def test_session_service_close_returns_timestamp_and_missing_session_raises() -> None:
    clock = FakeClock()
    service, _ = build_service(clock)
    opened = service.open_session(
        scope_type="desktop",
        scope_target=None,
        armed=False,
        dry_run=True,
        ttl_seconds=10,
    )

    clock.advance(seconds=4)
    closed = service.close_session(session_id=opened["session_id"])

    assert closed == {
        "session_id": opened["session_id"],
        "closed": True,
        "closed_at": "2026-03-09T00:00:04+00:00",
    }

    with pytest.raises(WispHandError) as exc_info:
        service.close_session(session_id="missing")
    assert exc_info.value.code == "session_not_found"
