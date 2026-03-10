from __future__ import annotations

TOOL_NAMESPACE = "wisp_hand"

IMPLEMENTED_TOOLS = [
    f"{TOOL_NAMESPACE}.capabilities",
    f"{TOOL_NAMESPACE}.session.open",
    f"{TOOL_NAMESPACE}.session.close",
    f"{TOOL_NAMESPACE}.desktop.get_topology",
    f"{TOOL_NAMESPACE}.cursor.get_position",
    f"{TOOL_NAMESPACE}.capture.screen",
    f"{TOOL_NAMESPACE}.wait",
    f"{TOOL_NAMESPACE}.capture.diff",
    f"{TOOL_NAMESPACE}.batch.run",
    f"{TOOL_NAMESPACE}.vision.describe",
    f"{TOOL_NAMESPACE}.vision.locate",
    f"{TOOL_NAMESPACE}.pointer.move",
    f"{TOOL_NAMESPACE}.pointer.click",
    f"{TOOL_NAMESPACE}.pointer.drag",
    f"{TOOL_NAMESPACE}.pointer.scroll",
    f"{TOOL_NAMESPACE}.keyboard.type",
    f"{TOOL_NAMESPACE}.keyboard.press",
]

