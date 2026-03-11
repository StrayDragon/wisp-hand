from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypedDict

from mcp.shared.exceptions import McpError
from mcp.types import ErrorData
from pydantic import BaseModel, ConfigDict

from wisp_hand.shared.types import JSONValue

MCP_ERROR_MAP: dict[str, int] = {
    "invalid_config": -32602,
    "invalid_parameters": -32602,
    "invalid_scope": -32602,
    "unsupported_environment": -32001,
    "dependency_missing": -32002,
    "capability_unavailable": -32003,
    "session_not_found": -32004,
    "session_expired": -32005,
    "policy_denied": -32006,
    "session_not_armed": -32007,
    "scope_violation": -32008,
    "internal_error": -32603,
}


class ErrorPayload(TypedDict):
    code: str
    message: str
    details: dict[str, JSONValue]


class ErrorPayloadModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: dict[str, Any]


@dataclass(slots=True)
class WispHandError(Exception):
    code: str
    message: str
    details: dict[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__init__(self.message)

    def to_payload(self) -> ErrorPayload:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }

    def to_mcp_error(self) -> McpError:
        return McpError(
            ErrorData(
                code=MCP_ERROR_MAP.get(self.code, -32603),
                message=self.message,
                data=self.to_payload(),
            )
        )


class ConfigError(WispHandError):
    def __init__(self, message: str, details: dict[str, JSONValue] | None = None) -> None:
        super().__init__("invalid_config", message, details or {})


def internal_error(reason: str) -> WispHandError:
    return WispHandError("internal_error", "Internal server error", {"reason": reason})
