from __future__ import annotations

import argparse
import json
from pathlib import Path

from fin_agent.backtest.runner import run_backtest
from fin_agent.data.importer import import_ohlcv_file
from fin_agent.storage.paths import RuntimePaths
from fin_agent.strategy.models import IntentSnapshot
from fin_agent.strategy.service import build_strategy_from_intent
from fin_agent.world_state.service import build_world_state_manifest


def cmd_import(args: argparse.Namespace) -> None:
    paths = RuntimePaths(root=Path(args.runtime_home))
    result = import_ohlcv_file(Path(args.path), paths)
    print(json.dumps(result.__dict__, indent=2))


def cmd_tracer(args: argparse.Namespace) -> None:
    paths = RuntimePaths(root=Path(args.runtime_home))
    intent = IntentSnapshot(
        universe=[args.symbol],
        start_date=args.start_date,
        end_date=args.end_date,
        initial_capital=args.initial_capital,
        short_window=args.short_window,
        long_window=args.long_window,
        max_positions=1,
    )
    strategy = build_strategy_from_intent(intent, args.strategy_name)
    manifest = build_world_state_manifest(paths, strategy.universe, strategy.start_date, strategy.end_date)
    run = run_backtest(paths, strategy, manifest)
    print(
        json.dumps(
            {
                "run_id": run.run_id,
                "strategy_name": run.strategy_name,
                "metrics": run.metrics.__dict__,
                "artifacts": run.artifacts.__dict__,
            },
            indent=2,
        )
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
