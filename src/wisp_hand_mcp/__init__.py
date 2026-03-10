from __future__ import annotations

"""
Distribution shim for `wisp-hand-mcp`.

The implementation lives in the `wisp_hand` package. This module exists to satisfy
the build backend's expectation that the normalized project name maps to a Python
package under `src/`.
"""

from wisp_hand import (  # noqa: F401
    RuntimeConfig,
    WispHandRuntime,
    WispHandServer,
    load_runtime_config,
)

__all__ = [
    "RuntimeConfig",
    "WispHandRuntime",
    "WispHandServer",
    "load_runtime_config",
]

