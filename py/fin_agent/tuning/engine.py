from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from itertools import product
import random
from typing import Any

from fin_agent.code_strategy.backtest import run_code_strategy_backtest
from fin_agent.storage.paths import RuntimePaths


def _metric_direction(metric_name: str) -> float:
    lowered = metric_name.lower()
    if "drawdown" in lowered:
        return -1.0
    if "stdev" in lowered or "volatility" in lowered:
        return -1.0
    return 1.0


@dataclass(frozen=True)
class _ParameterSpec:
    name: str
    kind: str
    min_value: float | int | None
    max_value: float | int | None
    values: tuple[Any, ...]
    step: float | None


@dataclass(frozen=True)
class _Objective:
    metric: str
    maximize: bool
    weights: dict[str, float]


def _parse_objective(payload: dict[str, Any] | None) -> _Objective:
    if payload is None:
        return _Objective(metric="sharpe", maximize=True, weights={"sharpe": 1.0})

    metric = str(payload.get("metric", "sharpe")).strip()
    if not metric:
        raise ValueError("objective.metric is required")

    maximize = bool(payload.get("maximize", True))
    raw_weights = payload.get("weights")

    weights: dict[str, float]
    if raw_weights is None:
        weights = {metric: 1.0 if maximize else -1.0}
    else:
        if not isinstance(raw_weights, dict):
            raise ValueError("objective.weights must be an object when provided")
        if not raw_weights:
            raise ValueError("objective.weights must not be empty")
        weights = {}
        for key, value in raw_weights.items():
            key_name = str(key).strip()
            if not key_name:
                raise ValueError("objective.weights contains empty metric name")
            try:
                raw_value = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"objective.weights[{key_name}] must be a numeric value; got {type(value).__name__}"
                ) from exc
            weights[key_name] = raw_value

    return _Objective(metric=metric, maximize=maximize, weights=weights)


def _coerce_float(value: Any, label: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric: {value}") from exc


def _coerce_int(value: Any, label: str) -> int:
    as_float = _coerce_float(value, label=label)
    if abs(as_float - int(as_float)) > 1e-12:
        raise ValueError(f"{label} must be integral: {value}")
    return int(round(as_float))


def _normalize_choice_values(name: str, raw: Any) -> _ParameterSpec:
    if not isinstance(raw, (list, tuple)):
        raise ValueError(f"{name}: choice parameters must be an array")
    if not raw:
        raise ValueError(f"{name}: choice list must not be empty")
    normalized = tuple(raw)
    return _ParameterSpec(
        name=name,
        kind="choice",
        min_value=None,
        max_value=None,
        values=normalized,
        step=None,
    )


def _normalize_range(name: str, cfg: dict[str, Any], expected_kind: str) -> _ParameterSpec:
    min_value = cfg.get("min")
    max_value = cfg.get("max")
    if min_value is None or max_value is None:
        raise ValueError(f"{name}: range specs require min and max")

    min_f = _coerce_float(min_value, label=f"{name}.min")
    max_f = _coerce_float(max_value, label=f"{name}.max")
    if max_f < min_f:
        raise ValueError(f"{name}: max must be >= min")

    step = cfg.get("step")
    step_f: float | None = None
    if step is not None:
        step_f = _coerce_float(step, label=f"{name}.step")
        if step_f <= 0:
            raise ValueError(f"{name}.step must be positive")

    if expected_kind == "int_range":
        if min_f != int(min_f) or max_f != int(max_f):
            raise ValueError(f"{name}: int_range min and max must be integer values")
        return _ParameterSpec(
            name=name,
            kind="int_range",
            min_value=int(min_f),
            max_value=int(max_f),
            values=(),
            step=step_f,
        )

    return _ParameterSpec(
        name=name,
        kind="float_range",
        min_value=min_f,
        max_value=max_f,
        values=(),
        step=step_f,
    )


def parse_search_space(raw_search_space: dict[str, Any]) -> list[_ParameterSpec]:
    if not isinstance(raw_search_space, dict):
        raise ValueError("search_space must be an object")
    if not raw_search_space:
        raise ValueError("search_space must include at least one parameter")

    specs: list[_ParameterSpec] = []
    for name, raw in raw_search_space.items():
        param_name = str(name).strip()
        if not param_name:
            raise ValueError("search_space contains empty parameter name")

        if isinstance(raw, dict):
            if "choices" in raw:
                specs.append(_normalize_choice_values(param_name, raw["choices"]))
                continue
            if "values" in raw and "type" not in raw and "kind" not in raw:
                specs.append(_normalize_choice_values(param_name, raw["values"]))
                continue

            t = str(raw.get("type") or raw.get("kind") or "float_range").strip().lower()
            if t in {"choice", "choices", "categorical"}:
                values = raw.get("values")
                if values is None:
                    raise ValueError(f"{param_name}: {t} requires 'values'")
                specs.append(_normalize_choice_values(param_name, values))
                continue

            if t in {"int", "int_range"}:
                specs.append(_normalize_range(param_name, raw, expected_kind="int_range"))
                continue
            if t in {"float", "float_range"}:
                specs.append(_normalize_range(param_name, raw, expected_kind="float_range"))
                continue

            raise ValueError(f"{param_name}: unsupported type '{t}'")

        specs.append(_normalize_choice_values(param_name, raw))

    return specs


def _round_to_step(value: float, step: float | None) -> float:
    if step is None or step <= 0:
        return float(value)
    return round(round(value / step) * step, 10)


def _coerce_param_for_grid(spec: _ParameterSpec, value: float) -> Any:
    if spec.kind == "choice":
        return value
    if spec.kind == "int_range":
        return int(_round_to_step(float(value), spec.step))
    if spec.kind == "float_range":
        return float(_round_to_step(float(value), spec.step))
    raise ValueError(f"unexpected spec kind: {spec.kind}")


def _candidate_values_from_anchor(
    spec: _ParameterSpec,
    layer: int,
    anchors: list[dict[str, Any]] | None,
) -> list[Any]:
    if spec.kind == "choice":
        return list(dict.fromkeys(spec.values))

    if spec.kind not in {"int_range", "float_range"}:
        raise ValueError(f"{spec.name}: unsupported range kind: {spec.kind}")

    min_value = _coerce_float(spec.min_value, label=f"{spec.name}.min")
    max_value = _coerce_float(spec.max_value, label=f"{spec.name}.max")
    span = max_value - min_value
    if span < 0:
        raise ValueError(f"{spec.name}: max must be >= min")

    if step := spec.step:
        values: list[Any] = []
        current = min_value
        while current <= max_value + (1e-12):
            values.append(_coerce_param_for_grid(spec, current))
            current += step

        if values[-1] != _coerce_param_for_grid(spec, max_value):
            values.append(_coerce_param_for_grid(spec, max_value))
        dedupe = list(dict.fromkeys(values))
        return dedupe

    if span == 0:
        return [_coerce_param_for_grid(spec, min_value)]

    if not anchors:
        # broad initial probes (min / mid / max)
        return [
            _coerce_param_for_grid(spec, min_value),
            _coerce_param_for_grid(spec, min_value + span / 2.0),
            _coerce_param_for_grid(spec, max_value),
        ]

    radius = span / float(2 ** (layer + 1))
    values: set[float] = set()
    for anchor in anchors:
        if spec.name not in anchor:
            continue
        try:
            anchor_value = float(anchor[spec.name])
        except (TypeError, ValueError):
            continue
        for delta in (0.0, -radius, radius):
            candidate = min(max_value, max(min_value, anchor_value + delta))
            values.add(float(candidate))

    if not values:
        return [
            _coerce_param_for_grid(spec, min_value),
            _coerce_param_for_grid(spec, min_value + span / 2.0),
            _coerce_param_for_grid(spec, max_value),
        ]

    return sorted(_coerce_param_for_grid(spec, value) for value in values)


def _generate_param_grid(specs: list[_ParameterSpec], layer: int, anchors: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    param_values: list[tuple[Any, ...]] = []

    for spec in specs:
        values = tuple(_candidate_values_from_anchor(spec, layer=layer, anchors=anchors))
        if not values:
            raise ValueError(f"failed to generate values for parameter '{spec.name}'")
        param_values.append(values)

    grid = []
    for row in product(*param_values):
        grid.append({specs[index].name: _coerce_param_for_grid(specs[index], float(value)) for index, value in enumerate(row)})
    return grid


def _score_candidate(metrics: dict[str, Any], objective: _Objective) -> tuple[float, str]:
    if not objective.weights:
        metric_value = _coerce_float(
            metrics.get(objective.metric),
            label=f"metrics[{objective.metric}]",
        )
        direction = _metric_direction(objective.metric)
        if not objective.maximize:
            direction *= -1.0
        score = metric_value * direction
        return score, objective.metric

    score = 0.0
    used_metrics: list[str] = []
    for metric, weight in objective.weights.items():
        if metric not in metrics:
            continue
        value = _coerce_float(metrics[metric], label=f"metrics[{metric}]")
        direction = _metric_direction(metric)
        used_metrics.append(metric)
        score += weight * direction * value

    if not used_metrics:
        raise ValueError("objective cannot be computed; no candidate metrics available")

    return score, ",".join(used_metrics)


def _run_candidate(
    paths: RuntimePaths,
    request_payload: dict[str, Any],
    params: dict[str, Any],
    objective: _Objective,
    run_code_fn: Callable[..., dict[str, Any]],
    context_seed: int | None,
) -> dict[str, Any]:
    if context_seed is not None:
        random.seed(context_seed)

    run = run_code_fn(
        paths=paths,
        strategy_name=request_payload["strategy_name"],
        source_code=request_payload["source_code"],
        universe=request_payload["universe"],
        start_date=request_payload["start_date"],
        end_date=request_payload["end_date"],
        initial_capital=request_payload["initial_capital"],
        timeout_seconds=request_payload["timeout_seconds"],
        memory_mb=request_payload["memory_mb"],
        cpu_seconds=request_payload["cpu_seconds"],
        context={
            "tuning_params": params,
            "base_context": request_payload["context"],
            "seed": context_seed,
        },
    )

    metrics = run.get("metrics", {})
    score, metric_used = _score_candidate(metrics, objective)
    return {
        "run_id": run["run_id"],
        "score": score,
        "score_metric": metric_used,
        "metrics": metrics,
        "params": params,
        "run_payload": run,
    }


def tune_strategy(
    *,
    paths: RuntimePaths,
    strategy_name: str,
    source_code: str,
    universe: list[str],
    start_date: str,
    end_date: str,
    initial_capital: float,
    search_space: dict[str, Any],
    objective: dict[str, Any] | None = None,
    max_trials: int = 12,
    max_layers: int = 2,
    keep_top: int = 1,
    timeout_seconds: int = 5,
    memory_mb: int = 256,
    cpu_seconds: int = 2,
    max_trials_per_layer: int | None = None,
    context: dict[str, Any] | None = None,
    use_optuna: bool = False,
    random_seed: int | None = None,
    run_code_fn: Callable[..., dict[str, Any]] | None = None,
    event_callback: Callable[[dict[str, Any]], None] | None = None,
    only_plan: bool = False,
) -> dict[str, Any]:
    if not strategy_name.strip():
        raise ValueError("strategy_name is required")
    if not source_code.strip():
        raise ValueError("source_code is required")
    if not universe:
        raise ValueError("universe is required")
    if max_trials <= 0:
        raise ValueError("max_trials must be positive")
    if max_layers <= 0:
        raise ValueError("max_layers must be positive")
    if keep_top <= 0:
        raise ValueError("keep_top must be positive")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if memory_mb <= 0:
        raise ValueError("memory_mb must be positive")
    if cpu_seconds <= 0:
        raise ValueError("cpu_seconds must be positive")
    if max_trials_per_layer is not None and max_trials_per_layer <= 0:
        raise ValueError("max_trials_per_layer must be positive")

    parsed_objective = _parse_objective(objective)
    specs = parse_search_space(search_space)
    if run_code_fn is None:
        run_code_fn = run_code_strategy_backtest

    base_context = dict(context or {})
    request_payload = {
        "strategy_name": strategy_name,
        "source_code": source_code,
        "universe": universe,
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": initial_capital,
        "timeout_seconds": timeout_seconds,
        "memory_mb": memory_mb,
        "cpu_seconds": cpu_seconds,
        "context": base_context,
    }

    candidate_plan: list[dict[str, Any]] = []
    for spec in specs:
        values = _candidate_values_from_anchor(spec=spec, layer=0, anchors=None)
        candidate_plan.append(
            {
                "parameter": spec.name,
                "kind": spec.kind,
                "sample_count": len(values),
                "sample_values": values[:12],
            }
        )

    if event_callback is not None:
        event_callback(
            {
                "event": "tuning.plan.ready",
                "requested_trials": max_trials,
                "max_layers": max_layers,
                "keep_top": keep_top,
                "candidate_plan": candidate_plan,
            }
        )

    if only_plan:
        return {
            "status": "planned",
            "objective": {
                "metric": parsed_objective.metric,
                "maximize": parsed_objective.maximize,
                "weights": parsed_objective.weights,
            },
            "evaluated_candidates": [],
            "best_candidate": None,
            "layer_decisions": [],
            "trials_attempted": 0,
            "trials_requested": int(max_trials),
            "candidate_plan": candidate_plan,
        }

    if use_optuna:
        raise ValueError("optuna execution is currently disabled in this build; set use_optuna=false")

    layer_decisions: list[dict[str, Any]] = []
    evaluated: list[dict[str, Any]] = []
    best_candidate: dict[str, Any] | None = None
    evaluated_param_sets: set[tuple[tuple[str, Any], ...]] = set()
    anchors: list[dict[str, Any]] = []
    remaining_trials = int(max_trials)
    rng = random.Random(random_seed)

    for layer in range(max_layers):
        if remaining_trials <= 0:
            break

        candidates = _generate_param_grid(specs, layer=layer, anchors=anchors if anchors else None)
        if not candidates:
            break
        if max_trials_per_layer is not None:
            candidates = candidates[:max_trials_per_layer]

        rng.shuffle(candidates)
        selected: list[dict[str, Any]] = []
        for candidate in candidates:
            key = tuple(sorted(candidate.items(), key=lambda item: item[0]))
            if key in evaluated_param_sets:
                continue
            evaluated_param_sets.add(key)
            selected.append(candidate)
            if len(selected) >= remaining_trials:
                break

        if not selected:
            break

        if event_callback is not None:
            event_callback(
                {
                    "event": "tuning.layer.started",
                    "layer": layer,
                    "requested": len(selected),
                    "remaining_trials": remaining_trials,
                }
            )

        layer_results: list[dict[str, Any]] = []
        for index, params in enumerate(selected):
            try:
                candidate_result = _run_candidate(
                    paths=paths,
                    request_payload=request_payload,
                    params=params,
                    objective=parsed_objective,
                    run_code_fn=run_code_fn,
                    context_seed=rng.randint(-(2**31), 2**31 - 1),
                )
            except Exception as exc:
                if event_callback is not None:
                    event_callback(
                        {
                            "event": "tuning.candidate.failed",
                            "layer": layer,
                            "candidate_index": index,
                            "params": params,
                            "error": str(exc),
                        }
                    )
                continue

            candidate = {
                "run_id": candidate_result["run_id"],
                "params": dict(candidate_result["params"]),
                "metrics": dict(candidate_result["metrics"]),
                "score": float(candidate_result["score"]),
                "score_metric": candidate_result["score_metric"],
                "layer": layer,
            }
            evaluated.append(candidate)
            layer_results.append(candidate)
            remaining_trials -= 1

            if event_callback is not None:
                event_callback(
                    {
                        "event": "tuning.candidate.evaluated",
                        "layer": layer,
                        "candidate_index": index,
                        "params": candidate["params"],
                        "metrics": candidate["metrics"],
                        "score": candidate["score"],
                        "run_id": candidate["run_id"],
                    }
                )

        if not layer_results:
            break

        layer_results.sort(key=lambda row: row["score"], reverse=True)
        top = layer_results[:keep_top]
        anchors = [row["params"] for row in top]
        layer_decisions.append(
            {
                "layer": f"layer_{layer}",
                "enabled": True,
                "reason": f"evaluated {len(selected)} candidates, retained top {len(top)}",
                "candidate_count": len(selected),
                "layer_kept": len(top),
            }
        )

        best_for_layer = top[0]
        if best_candidate is None or best_for_layer["score"] > best_candidate["score"]:
            best_candidate = best_for_layer

        if event_callback is not None:
            event_callback(
                {
                    "event": "tuning.layer.completed",
                    "layer": layer,
                    "best_score": best_for_layer["score"],
                    "attempted": len(layer_results),
                }
            )

    if best_candidate is None:
        raise ValueError("tuning run produced no successful candidates")

    return {
        "status": "completed",
        "objective": {
            "metric": parsed_objective.metric,
            "maximize": parsed_objective.maximize,
            "weights": parsed_objective.weights,
        },
        "evaluated_candidates": evaluated,
        "best_candidate": best_candidate,
        "layer_decisions": layer_decisions,
        "trials_attempted": len(evaluated),
        "trials_requested": int(max_trials),
    }
