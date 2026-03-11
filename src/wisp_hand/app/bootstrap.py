from __future__ import annotations

from pathlib import Path

from wisp_hand.infra.config import load_runtime_config
from wisp_hand.app.runtime import WispHandRuntime


def create_runtime(config_path: str | None = None) -> WispHandRuntime:
    path = None if config_path is None else Path(config_path)
    return WispHandRuntime(config=load_runtime_config(path))
