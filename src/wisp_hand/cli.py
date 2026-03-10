from __future__ import annotations

import argparse
import sys
from pathlib import Path

from wisp_hand.config import load_runtime_config
from wisp_hand.errors import WispHandError
from wisp_hand.observability import init_logging
from wisp_hand.runtime import WispHandRuntime
from wisp_hand.server import WispHandServer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wisp-hand")
    parser.add_argument("--config", type=Path, help="Path to the runtime TOML config file.")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        help="Override transport configured in the runtime config file.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        config = load_runtime_config(args.config)
        if args.transport is not None:
            server_config = config.server.model_copy(update={"transport": args.transport})
            config = config.model_copy(update={"server": server_config})
        try:
            init_logging(config)
        except Exception:
            # Logging should never prevent the server from starting.
            pass
        server = WispHandServer(WispHandRuntime(config=config))
        server.run()
    except WispHandError as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
