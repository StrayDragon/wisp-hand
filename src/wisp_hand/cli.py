from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from wisp_hand.infra.config import load_runtime_config
from wisp_hand.infra.discovery import build_discovery_report, runtime_version
from wisp_hand.shared.errors import WispHandError
from wisp_hand.infra.observability import init_logging
from wisp_hand.app.runtime import WispHandRuntime
from wisp_hand.protocol.mcp_server import WispHandServer


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", type=Path, help="Path to the runtime TOML config file.")
    common.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        help="Override transport configured in the runtime config file.",
    )

    parser = argparse.ArgumentParser(prog="wisp-hand")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", parents=[common], help="Run a runtime preflight check.")
    doctor.add_argument("--json", action="store_true", help="Emit a machine-readable JSON report to stdout.")

    subparsers.add_parser("mcp", parents=[common], help="Start the MCP server.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        command = args.command
        config = load_runtime_config(args.config)
        if args.transport is not None:
            server_config = config.server.model_copy(update={"transport": args.transport})
            config = config.model_copy(update={"server": server_config})

        if command == "doctor":
            report = build_discovery_report(config=config, include_path_checks=True)
            if args.json:
                print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
            else:
                print(json.dumps(report, ensure_ascii=True, sort_keys=True), file=sys.stderr)
            return 0 if report.get("status") == "ready" else 1

        if command != "mcp":
            raise WispHandError("invalid_parameters", "Unknown command", {"command": command})

        # Startup preflight (stderr-only, safe for stdio transport).
        report = build_discovery_report(config=config, include_path_checks=True)
        if report.get("status") != "ready":
            print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True), file=sys.stderr)
            return 1

        try:
            init_logging(config)
        except Exception:
            # Logging should never prevent the server from starting.
            pass
        server = WispHandServer(WispHandRuntime(config=config))
        server.run()
    except WispHandError as exc:
        if getattr(args, "command", None) == "doctor":
            payload = {
                "status": "blocked",
                "version": runtime_version(),
                "transport": getattr(args, "transport", None),
                "config_path": str(getattr(args, "config", "") or ""),
                "issues": [{**exc.to_payload(), "severity": "blocking"}],
            }
            print(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True))
        else:
            print(f"{exc.code}: {exc.message}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
