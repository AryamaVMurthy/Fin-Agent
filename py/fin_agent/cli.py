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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fin-agent")
    parser.add_argument("--runtime-home", default=".finagent")
    sub = parser.add_subparsers(required=True)

    import_cmd = sub.add_parser("import-ohlcv")
    import_cmd.add_argument("path")
    import_cmd.set_defaults(func=cmd_import)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
