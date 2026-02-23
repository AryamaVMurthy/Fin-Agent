from __future__ import annotations

import ast
import re
from dataclasses import dataclass

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_ALLOWED_BIN_OPS: dict[type[ast.operator], str] = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.Mod: "%",
}
_ALLOWED_CMP_OPS: dict[type[ast.cmpop], str] = {
    ast.Eq: "=",
    ast.NotEq: "!=",
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
}


@dataclass(frozen=True)
class FormulaValidation:
    valid: bool
    sql_expression: str
    identifiers: list[str]


def _literal_sql(value: object) -> str:
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    raise ValueError(f"unsupported literal type in formula: {type(value).__name__}")


def _compile_node(node: ast.AST, allowed_identifiers: set[str], identifiers: set[str]) -> str:
    if isinstance(node, ast.Expression):
        return _compile_node(node.body, allowed_identifiers, identifiers)

    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            op = "AND"
        elif isinstance(node.op, ast.Or):
            op = "OR"
        else:
            raise ValueError(f"unsupported boolean operator: {type(node.op).__name__}")
        values = [_compile_node(part, allowed_identifiers, identifiers) for part in node.values]
        return f"({' {} '.format(op).join(values)})"

    if isinstance(node, ast.BinOp):
        op = _ALLOWED_BIN_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"unsupported arithmetic operator: {type(node.op).__name__}")
        left = _compile_node(node.left, allowed_identifiers, identifiers)
        right = _compile_node(node.right, allowed_identifiers, identifiers)
        return f"({left} {op} {right})"

    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.Not):
            return f"(NOT {_compile_node(node.operand, allowed_identifiers, identifiers)})"
        if isinstance(node.op, ast.USub):
            return f"(-{_compile_node(node.operand, allowed_identifiers, identifiers)})"
        if isinstance(node.op, ast.UAdd):
            return f"(+{_compile_node(node.operand, allowed_identifiers, identifiers)})"
        raise ValueError(f"unsupported unary operator: {type(node.op).__name__}")

    if isinstance(node, ast.Compare):
        left = _compile_node(node.left, allowed_identifiers, identifiers)
        compiled: list[str] = []
        current_left = left
        for op, comparator in zip(node.ops, node.comparators):
            sql_op = _ALLOWED_CMP_OPS.get(type(op))
            if sql_op is None:
                raise ValueError(f"unsupported comparison operator: {type(op).__name__}")
            right = _compile_node(comparator, allowed_identifiers, identifiers)
            compiled.append(f"({current_left} {sql_op} {right})")
            current_left = right
        return "(" + " AND ".join(compiled) + ")"

    if isinstance(node, ast.Name):
        key = node.id.strip()
        if not key:
            raise ValueError("empty identifier is not allowed")
        if not _IDENTIFIER_RE.match(key):
            raise ValueError(f"invalid identifier in formula: {key}")
        if key not in allowed_identifiers:
            raise ValueError(
                f"unknown identifier in formula: {key}; allowed={sorted(allowed_identifiers)}"
            )
        identifiers.add(key)
        return key

    if isinstance(node, ast.Constant):
        return _literal_sql(node.value)

    raise ValueError(f"unsupported syntax node in formula: {type(node).__name__}")


def validate_and_compile_formula(formula: str, allowed_identifiers: list[str]) -> FormulaValidation:
    src = formula.strip()
    if not src:
        raise ValueError("formula is required")
    allowed = {item.strip() for item in allowed_identifiers if item.strip()}
    if not allowed:
        raise ValueError("allowed_identifiers must not be empty")

    try:
        expr = ast.parse(src, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"invalid formula syntax: {exc.msg}") from exc

    seen: set[str] = set()
    sql = _compile_node(expr, allowed, seen)
    return FormulaValidation(valid=True, sql_expression=sql, identifiers=sorted(seen))
