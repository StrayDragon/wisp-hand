from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Literal, NotRequired, TypedDict

from wisp_hand.infra.observability import render_json_line, scrub_event_dict
from wisp_hand.shared.errors import ErrorPayload
from wisp_hand.shared.types import JSONValue


class AuditRecord(TypedDict):
    timestamp: str
    tool_name: str
    status: Literal["ok", "error", "denied"]
    latency_ms: int
    runtime_instance_id: NotRequired[str]
    started_at: NotRequired[str]
    session_id: NotRequired[str | None]
    scope: NotRequired[JSONValue | None]
    result: NotRequired[JSONValue | None]
    error: NotRequired[ErrorPayload | None]
    batch_id: NotRequired[str | None]
    parent_tool_name: NotRequired[str | None]
    step_index: NotRequired[int | None]
    step_type: NotRequired[str | None]


class AuditLogger:
    def __init__(
        self,
        *,
        audit_file: Path | None,
        allow_sensitive: bool = False,
        max_bytes: int | None = None,
        backup_count: int = 0,
    ) -> None:
        self._audit_file = audit_file
        self._allow_sensitive = allow_sensitive
        self._max_bytes = max_bytes
        self._backup_count = backup_count
        self._lock = RLock()

    def _maybe_rotate(self) -> None:
        if self._audit_file is None or self._max_bytes is None:
            return
        if self._max_bytes <= 0:
            return

        try:
            current_size = self._audit_file.stat().st_size
        except FileNotFoundError:
            return
        except Exception:  # pragma: no cover - best-effort rotation
            return

        if current_size < self._max_bytes:
            return

        # Keep at most backup_count rotated files.
        if self._backup_count <= 0:
            try:
                self._audit_file.write_text("", encoding="utf-8")
            except Exception:  # pragma: no cover
                return
            return

        try:
            oldest = Path(str(self._audit_file) + f".{self._backup_count}")
            if oldest.exists():
                oldest.unlink()
        except Exception:  # pragma: no cover
            pass

        for idx in range(self._backup_count - 1, 0, -1):
            src = Path(str(self._audit_file) + f".{idx}")
            dst = Path(str(self._audit_file) + f".{idx + 1}")
            try:
                if src.exists():
                    src.replace(dst)
            except Exception:  # pragma: no cover
                continue

        try:
            self._audit_file.replace(Path(str(self._audit_file) + ".1"))
        except Exception:  # pragma: no cover
            return

    def record(self, payload: AuditRecord) -> None:
        with self._lock:
            if self._audit_file is not None:
                try:
                    self._maybe_rotate()
                    scrubbed = scrub_event_dict(
                        dict(payload),
                        allow_sensitive=self._allow_sensitive,
                    )
                    json_line = render_json_line(scrubbed)
                    self._audit_file.parent.mkdir(parents=True, exist_ok=True)
                    with self._audit_file.open("a", encoding="utf-8") as handle:
                        handle.write(json_line + "\n")
                except Exception:  # pragma: no cover - audit should never break tools
                    # Audit is best-effort: tool semantics must not depend on audit durability.
                    return
