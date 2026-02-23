from __future__ import annotations

import argparse
import json
from pathlib import Path

from fin_agent.data.importer import import_ohlcv_file
from fin_agent.storage.paths import RuntimePaths


def cmd_import(args: argparse.Namespace) -> None:
    paths = RuntimePaths(root=Path(args.runtime_home))
    result = import_ohlcv_file(Path(args.path), paths)
    print(json.dumps(result.__dict__, indent=2))


def cmd_tracer(args: argparse.Namespace) -> None:
    _ = RuntimePaths(root=Path(args.runtime_home))
    raise SystemExit(
        "run-tracer is disabled: legacy intent/manual strategy flow has been removed. "
        "Use the agentic code-strategy flow via /v1/code-strategy/* tools."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fin-agent")
    parser.add_argument("--runtime-home", default=".finagent")
    sub = parser.add_subparsers(required=True)

    import_cmd = sub.add_parser("import-ohlcv")
    import_cmd.add_argument("path")
    import_cmd.set_defaults(func=cmd_import)

    tracer_cmd = sub.add_parser("run-tracer")
    tracer_cmd.add_argument("--strategy-name", default="SMA Tracer")
    tracer_cmd.add_argument("--symbol", required=True)
    tracer_cmd.add_argument("--start-date", required=True)
    tracer_cmd.add_argument("--end-date", required=True)
    tracer_cmd.add_argument("--initial-capital", type=float, default=100000.0)
    tracer_cmd.add_argument("--short-window", type=int, default=5)
    tracer_cmd.add_argument("--long-window", type=int, default=20)
    tracer_cmd.set_defaults(func=cmd_tracer)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
