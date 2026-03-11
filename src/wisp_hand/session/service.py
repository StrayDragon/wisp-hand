from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from wisp_hand.desktop.scope import normalize_scope
from wisp_hand.session.models import SessionCloseResult, SessionOpenResult
from wisp_hand.session.store import SessionStore
from wisp_hand.shared.types import JSONValue


class SessionService:
    def __init__(
        self,
        *,
        session_store: SessionStore,
        default_armed: bool,
        default_dry_run: bool,
        runtime_instance_id: str,
        started_at: str,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_store = session_store
        self._default_armed = default_armed
        self._default_dry_run = default_dry_run
        self._runtime_instance_id = runtime_instance_id
        self._started_at = started_at
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def open_session(
        self,
        *,
        scope_type: str,
        scope_target: JSONValue | None,
        armed: bool | None,
        dry_run: bool | None,
        ttl_seconds: int | None,
    ) -> SessionOpenResult:
        requested_scope = normalize_scope(scope_type, scope_target)
        record = self._session_store.create_session(
            scope=requested_scope,
            armed=self._default_armed if armed is None else armed,
            dry_run=self._default_dry_run if dry_run is None else dry_run,
            ttl_seconds=ttl_seconds,
        )
        return {
            "runtime_instance_id": self._runtime_instance_id,
            "started_at": self._started_at,
            "session_id": record.session_id,
            "scope": record.scope,
            "armed": record.armed,
            "dry_run": record.dry_run,
            "expires_at": record.expires_at.isoformat(),
        }

    def close_session(self, *, session_id: str) -> SessionCloseResult:
        record = self._session_store.close_session(session_id)
        return {
            "session_id": record.session_id,
            "closed": True,
            "closed_at": self._now_provider().isoformat(),
        }
