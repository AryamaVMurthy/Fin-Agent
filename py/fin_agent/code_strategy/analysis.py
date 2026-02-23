from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any

from fin_agent.integrations.opencode_agent import run_agent_json_task
from fin_agent.storage import sqlite_store
from fin_agent.storage.paths import RuntimePaths


SYSTEM_PROMPT = "\n".join(
    [
        "You are Fin-Agent Strategy Analyst.",
        "Return ONLY a JSON object and no markdown.",
        "Decide suggestions from provided run metrics, trade rows, signal rows, and source code.",
        "Do not invent unavailable metrics; cite concrete evidence fields from input.",
        "Each suggestion must include a practical code patch or pseudo-patch.",
    ]
)


def _analysis_timeout_seconds() -> float:
    raw = str(os.environ.get("FIN_AGENT_ANALYSIS_AGENT_TIMEOUT_SECONDS", "120")).strip()
    try:
        timeout = float(raw)
    except ValueError as exc:
        raise ValueError(f"invalid FIN_AGENT_ANALYSIS_AGENT_TIMEOUT_SECONDS value: {raw}") from exc
    if timeout <= 0:
        raise ValueError("FIN_AGENT_ANALYSIS_AGENT_TIMEOUT_SECONDS must be positive")
    return timeout


def _read_csv_preview(path: str, *, limit: int = 80) -> list[dict[str, Any]]:
    csv_path = Path(path)
    if not csv_path.exists():
        raise ValueError(f"analysis artifact not found: {path}")
    rows: list[dict[str, Any]] = []
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for idx, row in enumerate(reader):
            if idx >= limit:
                break
            rows.append(dict(row))
    return rows


def _normalize_suggestion(index: int, row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ValueError(f"agent suggestion[{index}] must be object")

    required = ("title", "evidence", "expected_impact", "confidence", "patch")
    missing = [key for key in required if key not in row]
    if missing:
        raise ValueError(f"agent suggestion[{index}] missing keys: {missing}")

    confidence_raw = row.get("confidence")
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"agent suggestion[{index}].confidence must be numeric") from exc
    if confidence < 0.0 or confidence > 1.0:
        raise ValueError(f"agent suggestion[{index}].confidence must be between 0 and 1")

    title = str(row.get("title", "")).strip()
    evidence = str(row.get("evidence", "")).strip()
    impact = str(row.get("expected_impact", "")).strip()
    patch = str(row.get("patch", "")).strip()
    if not title or not evidence or not impact or not patch:
        raise ValueError(f"agent suggestion[{index}] has empty required text fields")

    normalized = {
        "title": title,
        "evidence": evidence,
        "expected_impact": impact,
        "confidence": confidence,
        "patch": patch,
    }
    if "risk_notes" in row:
        normalized["risk_notes"] = row.get("risk_notes")
    return normalized


def _build_analysis_prompt(
    *,
    run_id: str,
    source_code: str,
    run_payload: dict[str, Any],
    metrics: dict[str, Any],
    trade_preview: list[dict[str, Any]],
    signal_preview: list[dict[str, Any]],
    max_suggestions: int,
) -> str:
    input_payload = {
        "run_id": run_id,
        "max_suggestions": max_suggestions,
        "metrics": metrics,
        "run_payload": run_payload,
        "trade_preview": trade_preview,
        "signal_preview": signal_preview,
        "source_code": source_code,
    }
    schema = {
        "summary": "string",
        "suggestions": [
            {
                "title": "string",
                "evidence": "string",
                "expected_impact": "string",
                "confidence": "number between 0 and 1",
                "patch": "string",
                "risk_notes": "optional string",
            }
        ],
    }
    return (
        "Analyze the following code-strategy backtest context and return actionable improvement suggestions.\n"
        "Constraints:\n"
        f"- Return at most {max_suggestions} suggestions.\n"
        "- Evidence must reference concrete input details (metrics, trade rows, signal rows, code).\n"
        "- Output MUST be a JSON object only and must match this schema shape.\n"
        f"SCHEMA={json.dumps(schema, sort_keys=True)}\n"
        f"INPUT={json.dumps(input_payload, sort_keys=True, default=str)}"
    )


def analyze_code_strategy_run(
    paths: RuntimePaths,
    run_id: str,
    source_code: str,
    max_suggestions: int = 5,
) -> dict[str, Any]:
    if max_suggestions <= 0:
        raise ValueError("max_suggestions must be positive")
    if not source_code.strip():
        raise ValueError("source_code is required")

    run = sqlite_store.get_backtest_run(paths, run_id)
    payload = run.get("payload", {})
    if payload.get("mode") != "code_strategy":
        raise ValueError(f"run_id={run_id} is not a code_strategy backtest run")

    metrics = run.get("metrics", {})
    artifacts = run.get("artifacts", {})
    trade_path = str(artifacts.get("trade_blotter_path", "")).strip()
    signal_path = str(artifacts.get("signal_context_path", "")).strip()
    if not trade_path or not signal_path:
        raise ValueError("run artifacts missing trade_blotter_path/signal_context_path")

    trade_preview = _read_csv_preview(trade_path, limit=80)
    signal_preview = _read_csv_preview(signal_path, limit=120)

    prompt = _build_analysis_prompt(
        run_id=run_id,
        source_code=source_code,
        run_payload=payload,
        metrics=metrics,
        trade_preview=trade_preview,
        signal_preview=signal_preview,
        max_suggestions=max_suggestions,
    )

    response = run_agent_json_task(
        user_prompt=prompt,
        system_prompt=SYSTEM_PROMPT,
        timeout_seconds=_analysis_timeout_seconds(),
        session_title=f"Fin-Agent analyze {run_id}",
    )

    suggestions_raw = response.get("suggestions")
    if not isinstance(suggestions_raw, list):
        raise ValueError("agent response missing suggestions list")
    if len(suggestions_raw) == 0:
        raise ValueError("agent returned empty suggestions list")

    trimmed = suggestions_raw[:max_suggestions]
    suggestions = [_normalize_suggestion(idx, row) for idx, row in enumerate(trimmed)]

    summary = str(response.get("summary", "")).strip()
    if not summary:
        summary = "agent_analysis_completed"

    return {
        "run_id": run_id,
        "metrics": metrics,
        "summary": summary,
        "suggestions": suggestions,
        "suggestion_count": len(suggestions),
        "mode": "agent_orchestrated",
        "auto_apply": False,
    }
