from __future__ import annotations

import ast
import inspect
from typing import Any


REQUIRED_SIGNATURES = {
    "prepare": 2,
    "generate_signals": 3,
    "risk_rules": 2,
}


def _assert_required_functions_exist(tree: ast.AST) -> None:
    names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    for name in REQUIRED_SIGNATURES:
        if name not in names:
            raise ValueError(f"missing required function: {name}")


def _assert_callable_signatures(namespace: dict[str, Any]) -> None:
    for name, expected_params in REQUIRED_SIGNATURES.items():
        fn = namespace.get(name)
        if not callable(fn):
            raise ValueError(f"missing required function: {name}")
        sig = inspect.signature(fn)
        if len(sig.parameters) != expected_params:
            raise ValueError(
                f"invalid signature for {name}: expected {expected_params} args, got {len(sig.parameters)}"
            )


def validate_code_strategy_source(source_code: str) -> dict[str, Any]:
    if not source_code.strip():
        raise ValueError("source_code is empty")
    try:
        tree = ast.parse(source_code)
    except SyntaxError as exc:
        raise ValueError(f"syntax error in source_code: {exc}") from exc

    _assert_required_functions_exist(tree)
    namespace: dict[str, Any] = {}
    try:
        compiled = compile(tree, filename="<code_strategy>", mode="exec")
        exec(compiled, namespace)  # noqa: S102
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"failed to load strategy source: {exc}") from exc

    _assert_callable_signatures(namespace)

    try:
        prepare_output = namespace["prepare"]({}, {})
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"prepare raised exception during contract check: {exc}") from exc
    if not isinstance(prepare_output, dict):
        raise ValueError("prepare must return dict")

    try:
        signal_output = namespace["generate_signals"]([], prepare_output, {})
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"generate_signals raised exception during contract check: {exc}") from exc
    if not isinstance(signal_output, list):
        raise ValueError("generate_signals must return list")
    for row in signal_output:
        if not isinstance(row, dict):
            raise ValueError("generate_signals items must be dict")
        missing = [key for key in ("symbol", "signal") if key not in row]
        if missing:
            raise ValueError(f"generate_signals item missing keys: {missing}")

    try:
        risk_output = namespace["risk_rules"]([], {})
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"risk_rules raised exception during contract check: {exc}") from exc
    if not isinstance(risk_output, dict):
        raise ValueError("risk_rules must return dict")

    return {
        "valid": True,
        "required_functions": sorted(REQUIRED_SIGNATURES.keys()),
    }
