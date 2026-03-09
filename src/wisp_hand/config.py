from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from wisp_hand.errors import ConfigError

DEFAULT_CONFIG_PATH = Path("~/.config/wisp-hand/config.toml").expanduser()
DEFAULT_STATE_DIR = Path("~/.local/state/wisp-hand").expanduser()


class ServerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transport: Literal["stdio", "sse", "streamable-http"] = "stdio"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


class PathsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_dir: Path = DEFAULT_STATE_DIR
    audit_file: Path | None = DEFAULT_STATE_DIR / "audit.jsonl"
    text_log_file: Path | None = DEFAULT_STATE_DIR / "runtime.log"
    capture_dir: Path = DEFAULT_STATE_DIR / "captures"


class SessionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_ttl_seconds: int = 900
    max_ttl_seconds: int = 3600


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_armed: bool = False
    default_dry_run: bool = False
    max_actions_per_window: int = 16
    rate_limit_window_seconds: float = 1.0
    dangerous_shortcuts: list[str] = Field(
        default_factory=lambda: [
            "ctrl+alt+backspace",
            "ctrl+alt+delete",
            "super+l",
        ]
    )


class VisionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["disabled", "assist"] = "disabled"
    model: str | None = None
    base_url: str = "http://127.0.0.1:11434"
    timeout_seconds: float = 30.0
    max_image_edge: int = Field(default=1536, gt=0)
    max_tokens: int = Field(default=256, gt=0)
    max_concurrency: int = Field(default=1, gt=0)


class DependencyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_binaries: list[str] = Field(default_factory=lambda: ["hyprctl", "grim", "slurp"])
    optional_binaries: list[str] = Field(default_factory=lambda: ["wtype"])


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    server: ServerConfig = Field(default_factory=ServerConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    vision: VisionConfig = Field(default_factory=VisionConfig)
    dependencies: DependencyConfig = Field(default_factory=DependencyConfig)
    config_path: Path = DEFAULT_CONFIG_PATH


def load_runtime_config(config_path: Path | None = None) -> RuntimeConfig:
    path = _resolve_config_path(config_path)
    raw_config = _read_config_file(path)
    capture_dir_explicit = bool(
        isinstance(raw_config.get("paths"), dict) and "capture_dir" in raw_config["paths"]
    )

    try:
        config = RuntimeConfig.model_validate({**raw_config, "config_path": path})
    except ValidationError as exc:
        raise ConfigError(
            "Runtime configuration is invalid",
            {"path": str(path), "errors": exc.errors(include_url=False)},
        ) from exc

    resolved = _resolve_paths(config, base_dir=path.parent, capture_dir_explicit=capture_dir_explicit)
    _ensure_runtime_directories(resolved)
    return resolved


def _resolve_config_path(config_path: Path | None) -> Path:
    if config_path is not None:
        return config_path.expanduser().resolve()

    env_path = os.environ.get("WISP_HAND_CONFIG")
    if env_path:
        return Path(env_path).expanduser().resolve()

    return DEFAULT_CONFIG_PATH.resolve()


def _read_config_file(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}

    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(
            "Runtime configuration could not be parsed",
            {"path": str(path), "reason": str(exc)},
        ) from exc

    if not isinstance(data, dict):
        raise ConfigError("Runtime configuration root must be a TOML table", {"path": str(path)})

    return data


def _resolve_paths(
    config: RuntimeConfig,
    *,
    base_dir: Path,
    capture_dir_explicit: bool,
) -> RuntimeConfig:
    resolved_state_dir = _make_path_absolute(config.paths.state_dir, base_dir)
    paths = config.paths.model_copy(
        update={
            "state_dir": resolved_state_dir,
            "audit_file": _make_optional_path_absolute(config.paths.audit_file, base_dir),
            "text_log_file": _make_optional_path_absolute(config.paths.text_log_file, base_dir),
            "capture_dir": (
                _make_path_absolute(config.paths.capture_dir, base_dir)
                if capture_dir_explicit
                else resolved_state_dir / "captures"
            ),
        }
    )
    return config.model_copy(update={"paths": paths, "config_path": config.config_path.resolve()})


def _make_path_absolute(path: Path, base_dir: Path) -> Path:
    expanded = path.expanduser()
    if expanded.is_absolute():
        return expanded
    return (base_dir / expanded).resolve()


def _make_optional_path_absolute(path: Path | None, base_dir: Path) -> Path | None:
    if path is None:
        return None
    return _make_path_absolute(path, base_dir)


def _ensure_runtime_directories(config: RuntimeConfig) -> None:
    config.paths.state_dir.mkdir(parents=True, exist_ok=True)
    config.paths.capture_dir.mkdir(parents=True, exist_ok=True)
    for path in (config.paths.audit_file, config.paths.text_log_file):
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
