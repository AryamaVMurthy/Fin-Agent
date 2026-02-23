from __future__ import annotations

import itertools
import math
import uuid
from dataclasses import dataclass
from typing import Any

from fin_agent.backtest.runner import run_backtest
from fin_agent.storage import sqlite_store
from fin_agent.storage.paths import RuntimePaths
from fin_agent.strategy.models import StrategySpec
from fin_agent.world_state.service import build_world_state_manifest


RISK_MODE_WIDTH = {
    "safe": {"short": 1, "long": 2, "positions": 0},
    "balanced": {"short": 2, "long": 4, "positions": 1},
    "aggressive": {"short": 4, "long": 8, "positions": 2},
}
TUNABLE_PARAMS = ("short_window", "long_window", "max_positions", "cost_bps")
LAYER_TO_PARAMS: dict[str, tuple[str, ...]] = {
    "signal": ("short_window", "long_window"),
    "portfolio": ("max_positions",),
    "execution": ("cost_bps",),
}
ALLOWED_POLICY_MODES = {"agent_decides", "user_selected"}


@dataclass(frozen=True)
class TuningConstraints:
    max_drawdown_limit: float | None = None
    turnover_cap: int | None = None


def derive_search_space(strategy: StrategySpec, risk_mode: str) -> dict[str, list[float]]:
    mode = risk_mode.lower().strip()
    if mode not in RISK_MODE_WIDTH:
        raise ValueError(f"unsupported risk_mode={risk_mode}; expected one of: {sorted(RISK_MODE_WIDTH.keys())}")

    width = RISK_MODE_WIDTH[mode]
    short_values = sorted(
        {
            float(max(1, strategy.short_window - width["short"])),
            float(strategy.short_window),
            float(strategy.short_window + width["short"]),
        }
    )
    long_values = sorted(
        {
            float(max(2, strategy.long_window - width["long"])),
            float(strategy.long_window),
            float(strategy.long_window + width["long"]),
        }
    )
    max_position_values = sorted(
        {
            float(max(1, strategy.max_positions - width["positions"])),
            float(strategy.max_positions),
            float(strategy.max_positions + width["positions"]),
        }
    )
    cost_values = sorted(
        {
            float(max(0.0, strategy.cost_bps - 2.0)),
            float(strategy.cost_bps),
            float(strategy.cost_bps + 2.0),
        }
    )

    return {
        "short_window": short_values,
        "long_window": long_values,
        "max_positions": max_position_values,
        "cost_bps": cost_values,
    }


def _normalize_policy_mode(policy_mode: str) -> str:
    mode = policy_mode.strip().lower()
    if mode not in ALLOWED_POLICY_MODES:
        raise ValueError(f"unsupported policy_mode={policy_mode}; expected one of: {sorted(ALLOWED_POLICY_MODES)}")
    return mode


def _normalize_include_layers(include_layers: list[str] | None) -> list[str]:
    if include_layers is None:
        return []
    normalized = [layer.strip().lower() for layer in include_layers if layer and layer.strip()]
    if not normalized:
        return []
    unsupported = sorted(layer for layer in set(normalized) if layer not in LAYER_TO_PARAMS)
    if unsupported:
        raise ValueError(
            f"unsupported include_layers={unsupported}; expected subset of: {sorted(LAYER_TO_PARAMS.keys())}"
        )
    unique: list[str] = []
    for layer in normalized:
        if layer not in unique:
            unique.append(layer)
    return unique


def _normalize_float(value: Any, *, field_name: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric: {value}") from exc
    if not math.isfinite(numeric):
        raise ValueError(f"{field_name} must be finite: {value}")
    return numeric


def _normalize_search_space_values(values: list[float], *, field_name: str) -> list[float]:
    if not values:
        raise ValueError(f"search_space.{field_name} must be non-empty")
    normalized = sorted({_normalize_float(v, field_name=f"search_space.{field_name}") for v in values})
    if field_name == "cost_bps":
        if any(v < 0.0 for v in normalized):
            raise ValueError("search_space.cost_bps cannot be negative")
    else:
        if any(v <= 0.0 for v in normalized):
            raise ValueError(f"search_space.{field_name} must contain positive values")
        for v in normalized:
            if abs(v - round(v)) > 1e-9:
                raise ValueError(
                    f"search_space.{field_name} must contain integer-like values; got {v}"
                )
    return normalized


def _normalize_search_space_overrides(search_space_overrides: dict[str, list[float]] | None) -> dict[str, list[float]]:
    if not search_space_overrides:
        return {}
    normalized: dict[str, list[float]] = {}
    unsupported = sorted(key for key in search_space_overrides.keys() if key not in TUNABLE_PARAMS)
    if unsupported:
        raise ValueError(f"search_space_overrides has unsupported keys={unsupported}; expected subset of {list(TUNABLE_PARAMS)}")
    for key, values in search_space_overrides.items():
        normalized[key] = _normalize_search_space_values(list(values), field_name=key)
    return normalized


def _normalize_freeze_params(freeze_params: dict[str, float] | None) -> dict[str, float]:
    if not freeze_params:
        return {}
    unsupported = sorted(key for key in freeze_params.keys() if key not in TUNABLE_PARAMS)
    if unsupported:
        raise ValueError(f"freeze_params has unsupported keys={unsupported}; expected subset of {list(TUNABLE_PARAMS)}")

    normalized: dict[str, float] = {}
    for key, value in freeze_params.items():
        numeric = _normalize_float(value, field_name=f"freeze_params.{key}")
        if key == "cost_bps":
            if numeric < 0.0:
                raise ValueError("freeze_params.cost_bps cannot be negative")
        else:
            if numeric <= 0.0:
                raise ValueError(f"freeze_params.{key} must be positive")
            if abs(numeric - round(numeric)) > 1e-9:
                raise ValueError(
                    f"freeze_params.{key} must be integer-like; got {numeric}"
                )
        normalized[key] = numeric
    return normalized


def _strategy_default_value(strategy: StrategySpec, param_name: str) -> float:
    if param_name == "short_window":
        return float(strategy.short_window)
    if param_name == "long_window":
        return float(strategy.long_window)
    if param_name == "max_positions":
        return float(strategy.max_positions)
    if param_name == "cost_bps":
        return float(strategy.cost_bps)
    raise ValueError(f"unsupported param_name={param_name}")


def _estimate_trial_count(search_space: dict[str, list[float]]) -> int:
    estimate = 1
    for key in TUNABLE_PARAMS:
        estimate *= len(search_space[key])
    return estimate


def derive_tuning_plan(
    strategy: StrategySpec,
    risk_mode: str,
    optimization_target: str,
    *,
    policy_mode: str = "agent_decides",
    include_layers: list[str] | None = None,
    freeze_params: dict[str, float] | None = None,
    search_space_overrides: dict[str, list[float]] | None = None,
) -> dict[str, Any]:
    mode = _normalize_policy_mode(policy_mode)
    selected_layers = _normalize_include_layers(include_layers)
    if mode == "user_selected" and not selected_layers:
        raise ValueError("policy_mode=user_selected requires non-empty include_layers")

    base_search_space = derive_search_space(strategy, risk_mode)
    normalized_overrides = _normalize_search_space_overrides(search_space_overrides)
    normalized_freeze_params = _normalize_freeze_params(freeze_params)

    for key, values in normalized_overrides.items():
        base_search_space[key] = values

    if selected_layers:
        active_layers = selected_layers
    else:
        active_layers = list(LAYER_TO_PARAMS.keys())

    for layer_name, layer_params in LAYER_TO_PARAMS.items():
        if layer_name in active_layers:
            continue
        for param in layer_params:
            base_search_space[param] = [_strategy_default_value(strategy, param)]

    for param, frozen_value in normalized_freeze_params.items():
        base_search_space[param] = [frozen_value]

    normalized_search_space: dict[str, list[float]] = {}
    for param_name in TUNABLE_PARAMS:
        if param_name not in base_search_space:
            raise ValueError(f"search_space missing required key: {param_name}")
        normalized_search_space[param_name] = _normalize_search_space_values(
            list(base_search_space[param_name]),
            field_name=param_name,
        )

    has_valid_signal_combo = any(
        short_window < long_window
        for short_window in normalized_search_space["short_window"]
        for long_window in normalized_search_space["long_window"]
    )
    if not has_valid_signal_combo:
        raise ValueError(
            "tuning plan has no valid signal window combinations; ensure at least one short_window value is less than long_window"
        )

    layer_rows: list[dict[str, Any]] = []
    for layer_name, layer_params in LAYER_TO_PARAMS.items():
        enabled = layer_name in active_layers
        actively_tuned = [param for param in layer_params if len(normalized_search_space[param]) > 1]
        frozen = [param for param in layer_params if len(normalized_search_space[param]) == 1]
        if not enabled:
            reason = "disabled_by_layer_policy"
        elif actively_tuned:
            reason = "active_with_variable_parameters"
        else:
            reason = "active_but_fully_frozen"
        layer_rows.append(
            {
                "layer": layer_name,
                "enabled": enabled,
                "parameters": list(layer_params),
                "actively_tuned_parameters": actively_tuned,
                "frozen_parameters": frozen,
                "reason": reason,
            }
        )

    graph_nodes: list[dict[str, Any]] = [
        {
            "id": "objective",
            "node_type": "objective",
            "optimization_target": optimization_target,
        }
    ]
    graph_edges: list[dict[str, Any]] = []
    for layer in layer_rows:
        layer_id = f"layer:{layer['layer']}"
        graph_nodes.append(
            {
                "id": layer_id,
                "node_type": "layer",
                "layer": layer["layer"],
                "enabled": layer["enabled"],
                "reason": layer["reason"],
            }
        )
        graph_edges.append(
            {
                "source": "objective",
                "target": layer_id,
                "edge_type": "optimizes",
            }
        )
        for param_name in layer["parameters"]:
            param_id = f"param:{param_name}"
            graph_nodes.append(
                {
                    "id": param_id,
                    "node_type": "parameter",
                    "parameter": param_name,
                    "candidate_values": normalized_search_space[param_name],
                }
            )
            graph_edges.append(
                {
                    "source": layer_id,
                    "target": param_id,
                    "edge_type": "controls",
                }
            )

    reasoning: list[str] = [
        f"policy_mode={mode}",
        f"risk_mode={risk_mode.strip().lower()}",
        f"optimization_target={optimization_target.strip().lower()}",
        f"active_layers={active_layers}",
    ]
    if normalized_overrides:
        reasoning.append(f"applied_search_space_overrides={sorted(normalized_overrides.keys())}")
    if normalized_freeze_params:
        reasoning.append(f"applied_freeze_params={sorted(normalized_freeze_params.keys())}")

    return {
        "policy_mode": mode,
        "active_layers": active_layers,
        "layers": layer_rows,
        "search_space": normalized_search_space,
        "graph": {
            "nodes": graph_nodes,
            "edges": graph_edges,
        },
        "reasoning": reasoning,
        "estimated_trials": _estimate_trial_count(normalized_search_space),
        "freeze_params": normalized_freeze_params,
    }


def _score_metrics(metrics: dict[str, Any], target: str) -> float:
    t = target.lower().strip()
    if t == "sharpe":
        return float(metrics.get("sharpe", 0.0))
    if t == "cagr":
        return float(metrics.get("cagr", 0.0))
    if t == "total_return":
        return float(metrics.get("total_return", 0.0))
    raise ValueError("optimization_target must be one of: sharpe, cagr, total_return")


def _iter_candidates(search_space: dict[str, list[float]]) -> list[dict[str, float]]:
    for key in TUNABLE_PARAMS:
        if key not in search_space or not search_space[key]:
            raise ValueError(f"search_space missing required key: {key}")

    combos = itertools.product(
        sorted(search_space["short_window"]),
        sorted(search_space["long_window"]),
        sorted(search_space["max_positions"]),
        sorted(search_space["cost_bps"]),
    )
    candidates: list[dict[str, float]] = []
    for short_window, long_window, max_positions, cost_bps in combos:
        candidates.append(
            {
                "short_window": float(short_window),
                "long_window": float(long_window),
                "max_positions": float(max_positions),
                "cost_bps": float(cost_bps),
            }
        )
    return candidates


def _sensitivity_analysis(
    scored_runs: list[dict[str, Any]],
    best_candidate: dict[str, Any],
    optimization_target: str,
) -> dict[str, Any]:
    baseline_params = best_candidate["params"]
    baseline_score = float(best_candidate["score"])
    baseline_metrics = best_candidate["metrics"]

    sensitivity: dict[str, Any] = {}
    for param_name in TUNABLE_PARAMS:
        local_comparables: list[dict[str, Any]] = []
        for row in scored_runs:
            if float(row["params"][param_name]) == float(baseline_params[param_name]):
                continue
            same_context = True
            for other_param in TUNABLE_PARAMS:
                if other_param == param_name:
                    continue
                if float(row["params"][other_param]) != float(baseline_params[other_param]):
                    same_context = False
                    break
            if same_context:
                local_comparables.append(row)

        if not local_comparables:
            sensitivity[param_name] = {
                "optimization_target": optimization_target,
                "baseline_value": float(baseline_params[param_name]),
                "status": "insufficient_local_samples",
            }
            continue

        best_alternative = max(local_comparables, key=lambda row: float(row["score"]))
        alt_score = float(best_alternative["score"])
        sensitivity[param_name] = {
            "optimization_target": optimization_target,
            "baseline_value": float(baseline_params[param_name]),
            "alternative_value": float(best_alternative["params"][param_name]),
            "baseline_score": baseline_score,
            "alternative_score": alt_score,
            "score_delta": alt_score - baseline_score,
            "alternative_run_id": best_alternative["run_id"],
            "baseline_metrics": baseline_metrics,
            "alternative_metrics": best_alternative["metrics"],
            "status": "ok",
        }
    return sensitivity


def run_tuning(
    paths: RuntimePaths,
    strategy_name: str,
    base_strategy: StrategySpec,
    search_space: dict[str, list[float]],
    optimization_target: str,
    constraints: TuningConstraints,
    max_trials: int,
    tuning_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if max_trials <= 0:
        raise ValueError("max_trials must be positive")

    candidates = _iter_candidates(search_space)
    manifest = build_world_state_manifest(
        paths,
        universe=base_strategy.universe,
        start_date=base_strategy.start_date,
        end_date=base_strategy.end_date,
    )

    attempts = 0
    completed = 0
    rejected: list[dict[str, Any]] = []
    scored_runs: list[dict[str, Any]] = []

    for candidate in candidates:
        if attempts >= max_trials:
            break
        attempts += 1

        short_window = int(candidate["short_window"])
        long_window = int(candidate["long_window"])
        max_positions = int(candidate["max_positions"])
        cost_bps = float(candidate["cost_bps"])

        if short_window >= long_window:
            rejected.append(
                {
                    "params": candidate,
                    "reason": "invalid_windows_short_must_be_less_than_long",
                }
            )
            continue
        if len(base_strategy.universe) > max_positions:
            rejected.append(
                {
                    "params": candidate,
                    "reason": "max_positions_below_universe_size",
                }
            )
            continue

        strategy = base_strategy.model_copy(
            update={
                "strategy_name": f"{strategy_name}-trial-{attempts}",
                "short_window": short_window,
                "long_window": long_window,
                "max_positions": max_positions,
                "cost_bps": cost_bps,
            }
        )
        try:
            run = run_backtest(paths, strategy, manifest)
        except ValueError as exc:
            rejected.append(
                {
                    "params": candidate,
                    "reason": f"backtest_failed:{exc}",
                }
            )
            continue

        metrics = run.metrics.__dict__
        if constraints.max_drawdown_limit is not None and abs(float(metrics["max_drawdown"])) > float(
            constraints.max_drawdown_limit
        ):
            rejected.append(
                {
                    "params": candidate,
                    "reason": (
                        f"max_drawdown_limit_exceeded:{metrics['max_drawdown']:.6f}>"
                        f"{constraints.max_drawdown_limit:.6f}"
                    ),
                    "run_id": run.run_id,
                }
            )
            continue
        if constraints.turnover_cap is not None and int(metrics["trade_count"]) > int(constraints.turnover_cap):
            rejected.append(
                {
                    "params": candidate,
                    "reason": f"turnover_cap_exceeded:{metrics['trade_count']}>{constraints.turnover_cap}",
                    "run_id": run.run_id,
                }
            )
            continue

        completed += 1
        scored_runs.append(
            {
                "run_id": run.run_id,
                "params": candidate,
                "metrics": metrics,
                "score": _score_metrics(metrics, optimization_target),
            }
        )

    if not scored_runs:
        raise ValueError(
            "tuning produced zero valid candidates under active constraints; remediation: relax constraints or expand search_space"
        )

    best = max(scored_runs, key=lambda row: float(row["score"]))
    sensitivity = _sensitivity_analysis(scored_runs, best, optimization_target=optimization_target)
    tuning_run_id = uuid.uuid4().hex
    payload = {
        "tuning_run_id": tuning_run_id,
        "strategy_name": strategy_name,
        "optimization_target": optimization_target,
        "constraints": {
            "max_drawdown_limit": constraints.max_drawdown_limit,
            "turnover_cap": constraints.turnover_cap,
        },
        "attempted_trials": attempts,
        "completed_trials": completed,
        "trial_space_size": len(candidates),
        "search_space": search_space,
        "best_candidate": best,
        "top_candidates": sorted(scored_runs, key=lambda row: float(row["score"]), reverse=True)[:5],
        "evaluated_candidates": scored_runs,
        "rejected_candidates": rejected,
        "sensitivity_analysis": sensitivity,
        "tuning_plan": tuning_plan
        or {
            "policy_mode": "legacy",
            "active_layers": list(LAYER_TO_PARAMS.keys()),
            "reasoning": ["legacy_search_space_mode"],
        },
    }
    sqlite_store.save_tuning_run(paths, strategy_name=strategy_name, payload=payload)
    sqlite_store.append_audit_event(
        paths,
        "tuning.run",
        {
            "tuning_run_id": tuning_run_id,
            "strategy_name": strategy_name,
            "attempted_trials": attempts,
            "completed_trials": completed,
            "best_run_id": best["run_id"],
            "optimization_target": optimization_target,
        },
    )
    return payload
