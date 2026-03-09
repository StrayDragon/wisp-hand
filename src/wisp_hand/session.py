from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from threading import RLock
from uuid import uuid4

from wisp_hand.errors import WispHandError
from wisp_hand.models import ScopeEnvelope, SessionRecord


class SessionStore:
    def __init__(
        self,
        *,
        default_ttl_seconds: int,
        max_ttl_seconds: int,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._default_ttl_seconds = default_ttl_seconds
        self._max_ttl_seconds = max_ttl_seconds
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._active_sessions: dict[str, SessionRecord] = {}
        self._expired_sessions: set[str] = set()
        self._lock = RLock()

    def create_session(
        self,
        *,
        scope: ScopeEnvelope,
        armed: bool,
        dry_run: bool,
        ttl_seconds: int | None,
    ) -> SessionRecord:
        ttl = ttl_seconds or self._default_ttl_seconds
        if ttl <= 0 or ttl > self._max_ttl_seconds:
            raise WispHandError(
                "invalid_parameters",
                "ttl_seconds is outside the allowed range",
                {
                    "ttl_seconds": ttl,
                    "max_ttl_seconds": self._max_ttl_seconds,
                },
            )

        now = self._now_provider()
        record = SessionRecord(
            session_id=str(uuid4()),
            scope=scope,
            armed=armed,
            dry_run=dry_run,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl),
        )

        with self._lock:
            self._active_sessions[record.session_id] = record
            self._expired_sessions.discard(record.session_id)

        return record

    def get_session(self, session_id: str) -> SessionRecord:
        with self._lock:
            self._expire_sessions_locked()

            if session_id in self._expired_sessions:
                raise WispHandError(
                    "session_expired",
                    "Session has expired",
                    {"session_id": session_id},
                )

            record = self._active_sessions.get(session_id)
            if record is None:
                raise WispHandError(
                    "session_not_found",
                    "Session could not be found",
                    {"session_id": session_id},
                )

            return record

    def close_session(self, session_id: str) -> SessionRecord:
        with self._lock:
            self._expire_sessions_locked()
            record = self._active_sessions.pop(session_id, None)
            self._expired_sessions.discard(session_id)

        if record is None:
            raise WispHandError(
                "session_not_found",
                "Session could not be found",
                {"session_id": session_id},
            )

        return record

    def _expire_sessions_locked(self) -> None:
        now = self._now_provider()
        expired_ids = [
            session_id
            for session_id, record in self._active_sessions.items()
            if record.expires_at <= now
        ]
        for session_id in expired_ids:
            self._active_sessions.pop(session_id, None)
            self._expired_sessions.add(session_id)
