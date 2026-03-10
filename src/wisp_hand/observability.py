from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import structlog
from rich.console import Console
from rich.logging import RichHandler
from structlog.contextvars import clear_contextvars
from structlog.stdlib import ProcessorFormatter
from logging.handlers import RotatingFileHandler

from wisp_hand.config import LogFormat, LogLevel, RuntimeConfig

_OWNED_HANDLER_ATTR = "_wisp_hand_owned"


def _is_tty(stream) -> bool:
    try:
        return bool(stream.isatty())
    except Exception:  # pragma: no cover - defensive
        return False


def _truncate_string(value: str, *, limit: int) -> str:
    if limit <= 0:
        return ""
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)] + "..."


def _scrub_value(value: Any, *, allow_sensitive: bool, string_limit: int) -> Any:
    if allow_sensitive:
        return value

    if isinstance(value, dict):
        return {key: _scrub_value(val, allow_sensitive=allow_sensitive, string_limit=string_limit) for key, val in value.items()}

    if isinstance(value, list):
        return [_scrub_value(item, allow_sensitive=allow_sensitive, string_limit=string_limit) for item in value]

    if isinstance(value, tuple):  # pragma: no cover - only if external libs pass tuples
        return tuple(_scrub_value(item, allow_sensitive=allow_sensitive, string_limit=string_limit) for item in value)

    if isinstance(value, str):
        return _truncate_string(value, limit=string_limit)

    return value


def scrub_event_dict(
    event_dict: dict[str, Any],
    *,
    allow_sensitive: bool,
    string_limit: int = 4096,
) -> dict[str, Any]:
    """
    Best-effort scrubber for logs/audit payloads.

    Default policy:
    - never include raw keyboard input text in logs
    - never include raw base64 blobs (inline images / inline screenshots)
    - aggressively truncate long strings
    """
    if allow_sensitive:
        return event_dict

    # Scrub common binary/sensitive keys anywhere they appear.
    sensitive_keys = {"text", "inline_image", "inline_base64"}

    def scrub(obj: Any) -> Any:
        if isinstance(obj, dict):
            out: dict[str, Any] = {}
            for key, val in obj.items():
                if key in sensitive_keys and isinstance(val, str):
                    out[key] = f"<redacted len={len(val)}>"
                elif key in sensitive_keys:
                    out[key] = "<redacted>"
                else:
                    out[key] = scrub(val)
            return out
        if isinstance(obj, list):
            return [scrub(item) for item in obj]
        if isinstance(obj, tuple):  # pragma: no cover
            return tuple(scrub(item) for item in obj)
        if isinstance(obj, str):
            return _truncate_string(obj, limit=string_limit)
        return obj

    return scrub(event_dict)


def _add_component_from_record(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    if "component" in event_dict:
        return event_dict
    record = event_dict.get("_record")
    if hasattr(record, "name"):
        event_dict["component"] = getattr(record, "name")
    else:  # pragma: no cover - should always have record for stdlib logging
        event_dict["component"] = "wisp_hand"
    return event_dict


def _build_pre_chain(*, allow_sensitive: bool) -> list[Callable[[Any, str, dict[str, Any]], dict[str, Any]]]:
    timestamper = structlog.processors.TimeStamper(fmt="iso", key="timestamp")

    def scrubber(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        return scrub_event_dict(event_dict, allow_sensitive=allow_sensitive)

    return [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        _add_component_from_record,
        timestamper,
        structlog.processors.format_exc_info,
        scrubber,
    ]


def _renderer_for(format_name: LogFormat, *, for_file: bool, tty: bool) -> Callable[[Any, str, dict[str, Any]], str]:
    if format_name == "json":
        return structlog.processors.JSONRenderer(sort_keys=True, ensure_ascii=False)

    if format_name == "rich":
        if for_file:
            # Rich formatting is only meaningful for consoles.
            return structlog.processors.KeyValueRenderer(sort_keys=True)
        if not tty:
            return structlog.processors.KeyValueRenderer(sort_keys=True)
        return structlog.dev.ConsoleRenderer(colors=False)

    return structlog.processors.KeyValueRenderer(sort_keys=True)


def _make_handlers(config: RuntimeConfig) -> list[logging.Handler]:
    handlers: list[logging.Handler] = []

    # Console sink is always stderr. This protects stdio transport (stdout is protocol).
    if config.logging.console.enabled:
        console_tty = _is_tty(sys.stderr)
        fmt: LogFormat = config.logging.console.format
        if fmt == "rich" and not console_tty:
            fmt = "plain"

        if fmt == "rich":
            handler: logging.Handler = RichHandler(
                console=Console(stderr=True),
                rich_tracebacks=True,
                show_path=False,
            )
        else:
            handler = logging.StreamHandler(stream=sys.stderr)

        handler.setLevel(config.logging.level)
        handlers.append(handler)

    # File sink uses paths.runtime_log_file (runtime log) if configured.
    if config.logging.file.enabled and config.paths.runtime_log_file is not None:
        try:
            file_path = Path(config.paths.runtime_log_file)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            retention = config.retention.runtime_log
            if retention.max_bytes > 0:
                file_handler = RotatingFileHandler(
                    file_path,
                    maxBytes=retention.max_bytes,
                    backupCount=retention.backup_count,
                    encoding="utf-8",
                )
                try:
                    if file_path.exists() and file_path.stat().st_size >= retention.max_bytes:
                        file_handler.doRollover()
                except Exception:  # pragma: no cover - best-effort
                    pass
            else:  # pragma: no cover - schema prevents max_bytes<=0, but keep safe
                file_handler = logging.FileHandler(file_path, encoding="utf-8")
        except Exception:  # pragma: no cover - degrade on filesystem failures
            file_handler = None
        if file_handler is not None:
            file_handler.setLevel(config.logging.level)
            handlers.append(file_handler)

    # Attach ProcessorFormatter per-handler.
    pre_chain = _build_pre_chain(allow_sensitive=config.logging.allow_sensitive)
    for handler in handlers:
        is_file = isinstance(handler, logging.FileHandler)
        tty = _is_tty(sys.stderr) and not is_file
        desired_format = config.logging.file.format if is_file else config.logging.console.format
        if desired_format == "rich" and not tty and not is_file:
            desired_format = "plain"
        try:
            handler.setFormatter(
                ProcessorFormatter(
                    processor=_renderer_for(desired_format, for_file=is_file, tty=tty),
                    foreign_pre_chain=pre_chain,
                )
            )
        except Exception:  # pragma: no cover - last-ditch: keep default formatting
            pass
        setattr(handler, _OWNED_HANDLER_ATTR, True)

    return handlers


def _is_stdout_handler(handler: logging.Handler) -> bool:
    if not isinstance(handler, logging.StreamHandler):
        return False
    stream = getattr(handler, "stream", None)
    return stream in {sys.stdout, sys.__stdout__}


def _drop_owned_handlers(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        if getattr(handler, _OWNED_HANDLER_ATTR, False):
            logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:  # pragma: no cover - defensive
                pass


def _drop_stdout_handlers(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        if _is_stdout_handler(handler):
            logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:  # pragma: no cover - defensive
                pass


_ACTIVE_KEY: tuple[object, ...] | None = None


def init_logging(config: RuntimeConfig) -> None:
    """
    Initialize structlog + stdlib logging.

    This function is intentionally reconfigurable: tests create many runtimes with
    different state dirs, so we rebind file handlers when config changes.
    """
    global _ACTIVE_KEY

    try:
        key = (
            config.server.transport,
            str(config.paths.runtime_log_file) if config.paths.runtime_log_file is not None else None,
            config.logging.level,
            config.logging.console.enabled,
            config.logging.console.format,
            config.logging.file.enabled,
            config.logging.file.format,
            config.logging.allow_sensitive,
            os.getpid(),
        )
        if _ACTIVE_KEY == key:
            return

        root = logging.getLogger()
        if config.server.transport == "stdio":
            _drop_stdout_handlers(root)
        _drop_owned_handlers(root)

        try:
            handlers = _make_handlers(config)
        except Exception:  # pragma: no cover - defensive
            handlers = []

        if handlers:
            root.setLevel(config.logging.level)
            for handler in handlers:
                root.addHandler(handler)
        else:
            # Don't let logging crash the program: fall back to a safe stderr handler.
            handler = logging.StreamHandler(stream=sys.stderr)
            handler.setLevel(config.logging.level)
            setattr(handler, _OWNED_HANDLER_ATTR, True)
            root.setLevel(config.logging.level)
            root.addHandler(handler)

        # Configure structlog to emit through stdlib logging so FastMCP and our code share sinks.
        pre_chain = _build_pre_chain(allow_sensitive=config.logging.allow_sensitive)
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                *pre_chain,
                ProcessorFormatter.wrap_for_formatter,
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        clear_contextvars()

        _ACTIVE_KEY = key
    except Exception:  # pragma: no cover - last-ditch safety
        root = logging.getLogger()
        try:
            for handler in list(root.handlers):
                root.removeHandler(handler)
                handler.close()
        except Exception:
            pass

        handler = logging.StreamHandler(stream=sys.stderr)
        setattr(handler, _OWNED_HANDLER_ATTR, True)
        root.addHandler(handler)
        root.setLevel(config.logging.level)


def get_logger(component: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger("wisp_hand").bind(component=component)


def render_json_line(payload: dict[str, Any]) -> str:
    # Shared helper for audit writer to keep JSON stable.
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
