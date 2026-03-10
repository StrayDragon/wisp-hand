from __future__ import annotations

from pathlib import Path
from threading import RLock

from wisp_hand.models import AuditRecord
from wisp_hand.observability import render_json_line, scrub_event_dict


class AuditLogger:
    def __init__(
        self,
        *,
        audit_file: Path | None,
        allow_sensitive: bool = False,
    ) -> None:
        self._audit_file = audit_file
        self._allow_sensitive = allow_sensitive
        self._lock = RLock()

    def record(self, payload: AuditRecord) -> None:
        with self._lock:
            if self._audit_file is not None:
                try:
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
