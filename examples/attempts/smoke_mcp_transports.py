from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import tempfile
from pathlib import Path
from typing import Any

import anyio
import mcp.types as types
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def write_config(path: Path, *, transport: str, port: int | None) -> Path:
    host_line = 'host = "127.0.0.1"' if transport != "stdio" else ""
    port_line = f"port = {port}" if transport != "stdio" and port is not None else ""
    contents = f"""
[server]
transport = "{transport}"
{host_line}
{port_line}

[paths]
state_dir = "./state"
audit_file = "./state/audit.jsonl"
runtime_log_file = "./state/runtime.jsonl"

[dependencies]
required_binaries = []
optional_binaries = []
"""
    path.write_text(contents.strip() + "\n", encoding="utf-8")
    return path


async def run_smoke_over_session(session: ClientSession) -> dict[str, Any]:
    init = await session.initialize()
    tools = await session.list_tools()
    wait_tool = next(t for t in tools.tools if t.name == "wisp_hand.wait")
    wait_task_support = wait_tool.execution.taskSupport if wait_tool.execution is not None else None

    capabilities = await session.call_tool("wisp_hand.capabilities")
    opened = await session.call_tool("wisp_hand.session.open", {"scope_type": "desktop"})
    assert isinstance(opened.structuredContent, dict)
    session_id = opened.structuredContent["session_id"]
    assert isinstance(session_id, str) and session_id

    created = await session.experimental.call_tool_as_task(
        "wisp_hand.wait",
        {"session_id": session_id, "duration_ms": 200},
        ttl=30_000,
    )
    task_id = created.task.taskId

    statuses: list[dict[str, Any]] = []
    async for status in session.experimental.poll_task(task_id):
        statuses.append(
            {
                "status": status.status,
                "statusMessage": status.statusMessage,
                "pollInterval": status.pollInterval,
            }
        )

    result = await session.experimental.get_task_result(task_id, types.CallToolResult)

    return {
        "initialize": init.model_dump(mode="json", by_alias=True),
        "tools": {
            "count": len(tools.tools),
            "wait_taskSupport": wait_task_support,
        },
        "capabilities": capabilities.structuredContent,
        "session_id": session_id,
        "task": {
            "task_id": task_id,
            "status_history": statuses,
            "result": result.structuredContent,
        },
    }


async def main_async(args: argparse.Namespace) -> int:
    transport: str = args.transport
    out_path: Path | None = Path(args.out) if args.out else None

    with tempfile.TemporaryDirectory(prefix="wisp-hand-smoke-") as temp_root_str:
        temp_root = Path(temp_root_str)
        port = free_tcp_port() if transport != "stdio" else None
        config_path = write_config(
            temp_root / "config.toml",
            transport=transport,
            port=port,
        )

        env = {
            "HYPRLAND_INSTANCE_SIGNATURE": os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "fixture"),
            "PYTHONPATH": str(repo_root() / "src"),
        }

        result: dict[str, Any]
        if transport == "stdio":
            server = StdioServerParameters(
                command=sys.executable,
                args=["-m", "wisp_hand", "mcp", "--config", str(config_path)],
                env=env,
                cwd=repo_root(),
            )
            async with stdio_client(server) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    result = await run_smoke_over_session(session)
        elif transport == "sse":
            if port is None:
                raise RuntimeError("port was not set for sse transport")

            proc = await anyio.open_process(
                [sys.executable, "-m", "wisp_hand", "mcp", "--config", str(config_path)],
                env={**os.environ, **env},
                cwd=repo_root(),
                stdout=sys.stdout,
                stderr=sys.stderr,
            )
            try:
                url = f"http://127.0.0.1:{port}/sse"
                # Wait for server to accept connections.
                last_exc: Exception | None = None
                for _ in range(50):
                    try:
                        async with sse_client(url, timeout=2) as (read_stream, write_stream):
                            async with ClientSession(read_stream, write_stream) as session:
                                result = await run_smoke_over_session(session)
                        break
                    except Exception as exc:  # pragma: no cover - best effort retries
                        last_exc = exc
                        await anyio.sleep(0.1)
                else:
                    raise RuntimeError(f"Failed to connect to SSE server: {last_exc!r}")
            finally:
                proc.terminate()
                with anyio.move_on_after(2):
                    await proc.wait()
                if proc.returncode is None:  # pragma: no cover
                    proc.kill()
        else:
            raise ValueError(f"Unsupported transport: {transport}")

    if out_path is not None:
        out_path.write_text(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    else:
        print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="smoke_mcp_transports")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    parser.add_argument("--out", help="Optional path to write JSON result.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return anyio.run(lambda: main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
