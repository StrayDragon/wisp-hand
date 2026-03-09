from __future__ import annotations

from typing import cast

from wisp_hand.errors import WispHandError
from wisp_hand.models import JSONValue, ScopeEnvelope, ScopeType


def normalize_scope(scope_type: ScopeType, scope_target: JSONValue | None) -> ScopeEnvelope:
    target = _normalize_target(scope_type, scope_target)
    return {
        "type": scope_type,
        "target": target,
        "coordinate_space": {
            "origin": "scope",
            "units": "px",
            "relative_to": scope_type,
        },
        "constraints": {
            "input_relative": True,
        },
    }


def _normalize_target(scope_type: ScopeType, scope_target: JSONValue | None) -> JSONValue:
    if scope_type == "desktop":
        return {"kind": "virtual-desktop"}

    if scope_type == "region":
        region = _require_mapping(scope_target, scope_type)
        normalized = {
            "x": _require_int(region, "x"),
            "y": _require_int(region, "y"),
            "width": _require_positive_int(region, "width"),
            "height": _require_positive_int(region, "height"),
        }
        return normalized

    if scope_type == "window-follow-region":
        target = _require_mapping(scope_target, scope_type)
        if "window" not in target or "region" not in target:
            raise WispHandError(
                "invalid_scope",
                "window-follow-region scope requires window and region keys",
                {"scope_type": scope_type},
            )
        return {
            "window": cast(JSONValue, target["window"]),
            "region": _normalize_target("region", cast(JSONValue, target["region"])),
        }

    if scope_type in {"monitor", "window"}:
        if scope_target is None:
            raise WispHandError(
                "invalid_scope",
                f"{scope_type} scope requires a non-empty selector",
                {"scope_type": scope_type},
            )
        return {"selector": scope_target}

    raise WispHandError("invalid_scope", "Unsupported scope type", {"scope_type": scope_type})


def _require_mapping(scope_target: JSONValue | None, scope_type: ScopeType) -> dict[str, JSONValue]:
    if not isinstance(scope_target, dict):
        raise WispHandError(
            "invalid_scope",
            f"{scope_type} scope requires a JSON object target",
            {"scope_type": scope_type},
        )
    return scope_target


def _require_int(mapping: dict[str, JSONValue], key: str) -> int:
    value = mapping.get(key)
    if not isinstance(value, int):
        raise WispHandError("invalid_scope", f"{key} must be an integer", {"field": key})
    return value


def _require_positive_int(mapping: dict[str, JSONValue], key: str) -> int:
    value = _require_int(mapping, key)
    if value <= 0:
        raise WispHandError("invalid_scope", f"{key} must be greater than zero", {"field": key})
    return value
