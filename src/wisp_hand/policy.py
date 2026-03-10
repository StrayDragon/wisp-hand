from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from threading import RLock
from time import monotonic

from wisp_hand.errors import WispHandError
from wisp_hand.models import JSONValue

KEY_ALIASES = {
    "cmd": "super",
    "command": "super",
    "control": "ctrl",
    "meta": "super",
}


def normalize_key_name(key: str) -> str:
    normalized = key.strip().lower()
    if not normalized:
        raise WispHandError("invalid_parameters", "key names must not be empty")
    return KEY_ALIASES.get(normalized, normalized)


def normalize_shortcut(shortcut: Sequence[str] | str) -> str:
    if isinstance(shortcut, str):
        parts = [segment for segment in shortcut.split("+") if segment.strip()]
    else:
        parts = list(shortcut)

    normalized = [normalize_key_name(part) for part in parts]
    if not normalized:
        raise WispHandError("invalid_parameters", "shortcut must include at least one key")
    return "+".join(normalized)


@dataclass(frozen=True, slots=True)
class EmergencyStopState:
    reason: str
    triggered_at: float


class InputPolicy:
    def __init__(
        self,
        *,
        max_actions_per_window: int,
        rate_limit_window_seconds: float,
        dangerous_shortcuts: Sequence[str],
        monotonic_provider: Callable[[], float] | None = None,
    ) -> None:
        self._max_actions_per_window = max_actions_per_window
        self._rate_limit_window_seconds = rate_limit_window_seconds
        self._dangerous_shortcuts = {normalize_shortcut(item) for item in dangerous_shortcuts}
        self._monotonic_provider = monotonic_provider or monotonic
        self._recent_actions: dict[str, deque[float]] = defaultdict(deque)
        self._emergency_stop: EmergencyStopState | None = None
        self._lock = RLock()

    def trigger_emergency_stop(self, *, reason: str = "manual") -> None:
        with self._lock:
            self._emergency_stop = EmergencyStopState(
                reason=reason,
                triggered_at=self._monotonic_provider(),
            )

    def clear_emergency_stop(self) -> None:
        with self._lock:
            self._emergency_stop = None

    def evaluate(
        self,
        *,
        session_id: str,
        tool_name: str,
        action: dict[str, JSONValue],
    ) -> None:
        with self._lock:
            self._ensure_not_emergency_stopped()
            self._ensure_not_dangerous_shortcut(tool_name=tool_name, action=action)
            self._check_rate_limit(session_id=session_id)

    def _ensure_not_emergency_stopped(self) -> None:
        if self._emergency_stop is None:
            return

        raise WispHandError(
            "policy_denied",
            "Emergency stop is active",
            {
                "reason": "emergency_stop_latched",
                "trigger_reason": self._emergency_stop.reason,
            },
        )

    def _ensure_not_dangerous_shortcut(
        self,
        *,
        tool_name: str,
        action: dict[str, JSONValue],
    ) -> None:
        if tool_name != "wisp_hand.keyboard.press":
            return

        keys = action.get("keys")
        if not isinstance(keys, list):
            return

        shortcut = normalize_shortcut([str(item) for item in keys])
        if shortcut in self._dangerous_shortcuts:
            raise WispHandError(
                "policy_denied",
                "Requested shortcut is denied by policy",
                {
                    "reason": "dangerous_shortcut",
                    "shortcut": shortcut,
                },
            )

    def _check_rate_limit(self, *, session_id: str) -> None:
        now = self._monotonic_provider()
        bucket = self._recent_actions[session_id]

        while bucket and now - bucket[0] >= self._rate_limit_window_seconds:
            bucket.popleft()

        if len(bucket) >= self._max_actions_per_window:
            raise WispHandError(
                "policy_denied",
                "Input action rate limit exceeded",
                {
                    "reason": "rate_limit",
                    "max_actions_per_window": self._max_actions_per_window,
                    "rate_limit_window_seconds": self._rate_limit_window_seconds,
                },
            )

        bucket.append(now)
