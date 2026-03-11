from __future__ import annotations

import sys
from pathlib import Path

import anyio
import mcp.types as types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def write_config(path: Path, contents: str) -> Path:
    path.write_text(contents.strip() + "\n", encoding="utf-8")
    return path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_task_augmented_tools_call_matches_sync_result(tmp_path: Path) -> None:
    async def main() -> None:
        config_path = write_config(
            tmp_path / "config.toml",
            """
[server]
transport = "stdio"

[paths]
state_dir = "./state"
audit_file = "./state/audit.jsonl"
runtime_log_file = "./state/runtime.jsonl"

[dependencies]
required_binaries = []
optional_binaries = []
""",
        )

        env = {
            "HYPRLAND_INSTANCE_SIGNATURE": "fixture",
            "PYTHONPATH": str(repo_root() / "src"),
        }
        server = StdioServerParameters(
            command=sys.executable,
            args=["-m", "wisp_hand", "mcp", "--config", str(config_path)],
            env=env,
            cwd=repo_root(),
        )

        async with stdio_client(server) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                opened = await session.call_tool("wisp_hand.session.open", {"scope_type": "desktop"})
                assert isinstance(opened.structuredContent, dict)
                session_id = opened.structuredContent["session_id"]
                assert isinstance(session_id, str) and session_id

                sync_result = await session.call_tool(
                    "wisp_hand.wait", {"session_id": session_id, "duration_ms": 50}
                )
                task_ref = await session.experimental.call_tool_as_task(
                    "wisp_hand.wait", {"session_id": session_id, "duration_ms": 50}, ttl=30_000
                )
                task_id = task_ref.task.taskId

                status = await session.experimental.get_task(task_id)
                while status.status == "working":
                    assert status.statusMessage is not None and status.statusMessage != ""
                    await anyio.sleep(((status.pollInterval or 50) / 1000.0))
                    status = await session.experimental.get_task(task_id)

                assert status.status == "completed"
                assert status.statusMessage is not None and status.statusMessage != ""

                task_result = await session.experimental.get_task_result(task_id, types.CallToolResult)
                assert isinstance(sync_result.structuredContent, dict)
                assert isinstance(task_result.structuredContent, dict)

                # wait() includes timing jitter; we assert deterministic fields + schema shape.
                assert set(task_result.structuredContent) == set(sync_result.structuredContent)
                assert task_result.structuredContent["session_id"] == session_id
                assert task_result.structuredContent["duration_ms"] == 50
                assert isinstance(task_result.structuredContent["elapsed_ms"], int)
                assert task_result.structuredContent["elapsed_ms"] >= 0

    anyio.run(main)


def test_task_cancel_keeps_terminal_status(tmp_path: Path) -> None:
    async def main() -> None:
        config_path = write_config(
            tmp_path / "config.toml",
            """
[server]
transport = "stdio"

[paths]
state_dir = "./state"
audit_file = "./state/audit.jsonl"
runtime_log_file = "./state/runtime.jsonl"

[dependencies]
required_binaries = []
optional_binaries = []
""",
        )

        env = {
            "HYPRLAND_INSTANCE_SIGNATURE": "fixture",
            "PYTHONPATH": str(repo_root() / "src"),
        }
        server = StdioServerParameters(
            command=sys.executable,
            args=["-m", "wisp_hand", "mcp", "--config", str(config_path)],
            env=env,
            cwd=repo_root(),
        )

        async with stdio_client(server) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                opened = await session.call_tool("wisp_hand.session.open", {"scope_type": "desktop"})
                assert isinstance(opened.structuredContent, dict)
                session_id = opened.structuredContent["session_id"]
                assert isinstance(session_id, str) and session_id

                task_ref = await session.experimental.call_tool_as_task(
                    "wisp_hand.wait", {"session_id": session_id, "duration_ms": 2_000}, ttl=30_000
                )
                task_id = task_ref.task.taskId

                cancelled = await session.experimental.cancel_task(task_id)
                assert cancelled.status == "cancelled"

                # Give the background worker a chance to race and ensure status remains terminal.
                await anyio.sleep(0.05)
                status = await session.experimental.get_task(task_id)
                assert status.status == "cancelled"

    anyio.run(main)
