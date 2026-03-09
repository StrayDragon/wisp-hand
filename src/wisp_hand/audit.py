from __future__ import annotations

import json
from pathlib import Path
from threading import RLock

from wisp_hand.models import AuditRecord


class AuditLogger:
    def __init__(
        self,
        *,
        text_log_file: Path | None,
        audit_file: Path | None,
    ) -> None:
        self._text_log_file = text_log_file
        self._audit_file = audit_file
        self._lock = RLock()

    def record(self, payload: AuditRecord) -> None:
        text_line = self._format_text_line(payload)
        json_line = json.dumps(payload, ensure_ascii=True, sort_keys=True)

        with self._lock:
            if self._text_log_file is not None:
                self._text_log_file.parent.mkdir(parents=True, exist_ok=True)
                with self._text_log_file.open("a", encoding="utf-8") as handle:
                    handle.write(text_line + "\n")

            if self._audit_file is not None:
                self._audit_file.parent.mkdir(parents=True, exist_ok=True)
                with self._audit_file.open("a", encoding="utf-8") as handle:
                    handle.write(json_line + "\n")

    @staticmethod
    def _format_text_line(payload: AuditRecord) -> str:
        parts = [
            payload["timestamp"],
            payload["tool_name"],
            payload["status"],
            f"{payload['latency_ms']}ms",
        ]
        if "session_id" in payload and payload["session_id"] is not None:
            parts.append(f"session={payload['session_id']}")
        if "error" in payload and payload["error"] is not None:
            parts.append(f"error={payload['error']['code']}")
        return " | ".join(parts)
