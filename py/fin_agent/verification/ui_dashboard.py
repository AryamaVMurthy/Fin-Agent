from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any


_REQUIRED_HTTP_ARTIFACTS = {
    "backtest": "code-backtest-b.json",
    "analysis": "code-analyze.json",
    "trade_blotter": "visualize-trade-blotter.json",
    "boundary": "visualize-boundary.json",
}


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"{label} missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} invalid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be an object: {path}")
    return payload


def _require_dict(container: dict[str, Any], key: str, *, context: str) -> dict[str, Any]:
    value = container.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{context} missing required object field: {key}")
    return value


def _require_list(container: dict[str, Any], key: str, *, context: str) -> list[Any]:
    value = container.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{context} missing required list field: {key}")
    return value


def _require_str(container: dict[str, Any], key: str, *, context: str) -> str:
    value = container.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} missing required string field: {key}")
    return value


def _load_http_response(http_dir: Path, suffix: str) -> dict[str, Any]:
    matches = sorted(http_dir.glob(f"*-{suffix}"))
    if not matches:
        raise ValueError(f"missing required HTTP artifact: *-{suffix} in {http_dir}")
    if len(matches) > 1:
        matched = ", ".join(str(path.name) for path in matches)
        raise ValueError(f"multiple HTTP artifacts matched *-{suffix}: {matched}")
    payload = _read_json(matches[0], label="http artifact")
    if "response" not in payload:
        raise ValueError(f"http artifact missing response payload: {matches[0]}")
    response = payload["response"]
    if not isinstance(response, dict):
        raise ValueError(f"http artifact response must be object: {matches[0]}")
    return response


def _as_float(value: Any, *, context: str, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{context}.{field} must be numeric, got bool")
    if isinstance(value, (int, float)):
        return float(value)
    raise ValueError(f"{context}.{field} must be numeric, got {type(value).__name__}")


def _fmt_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _to_workspace_url(path_value: str, *, workspace_root: Path, context: str, field: str) -> tuple[str, str]:
    raw_path = Path(path_value).expanduser().resolve()
    if not raw_path.exists():
        raise ValueError(f"{context}.{field} path does not exist: {raw_path}")
    try:
        rel = raw_path.relative_to(workspace_root)
    except ValueError as exc:
        raise ValueError(
            f"{context}.{field} path is outside workspace root: path={raw_path} workspace_root={workspace_root}"
        ) from exc
    return str(raw_path), "/" + rel.as_posix()


def _render_responsive_table(headers: list[str], rows: list[list[Any]]) -> str:
    parts = ['<div class="table-wrap"><table class="responsive-table">', "<thead><tr>"]
    for header in headers:
        parts.append(f"<th>{escape(header)}</th>")
    parts.append("</tr></thead><tbody>")
    for row in rows:
        parts.append("<tr>")
        padded = row + [""] * (len(headers) - len(row))
        for idx, header in enumerate(headers):
            parts.append(f'<td data-label="{escape(header)}">{escape(_fmt_value(padded[idx]))}</td>')
        parts.append("</tr>")
    parts.append("</tbody></table></div>")
    return "".join(parts)


def generate_rigorous_ui_dashboard(run_dir: Path, workspace_root: Path | None = None) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    workspace_root = (workspace_root or Path.cwd()).resolve()
    artifacts_dir = run_dir / "artifacts"
    http_dir = artifacts_dir / "http"
    ui_dir = artifacts_dir / "ui"
    ui_dir.mkdir(parents=True, exist_ok=True)

    summary = _read_json(artifacts_dir / "summary.json", label="summary")
    if not isinstance(summary.get("status"), str):
        raise ValueError("summary missing required string field: status")
    generated_at = _require_str(summary, "generated_at", context="summary")

    responses: dict[str, dict[str, Any]] = {}
    for key, suffix in _REQUIRED_HTTP_ARTIFACTS.items():
        responses[key] = _load_http_response(http_dir, suffix)

    backtest = responses["backtest"]
    backtest_metrics = _require_dict(backtest, "metrics", context="backtest")
    backtest_artifacts = _require_dict(backtest, "artifacts", context="backtest")
    _require_str(backtest, "strategy_version_id", context="backtest")

    equity_abs, equity_url = _to_workspace_url(
        _require_str(backtest_artifacts, "equity_curve_path", context="backtest.artifacts"),
        workspace_root=workspace_root,
        context="backtest.artifacts",
        field="equity_curve_path",
    )
    drawdown_abs, drawdown_url = _to_workspace_url(
        _require_str(backtest_artifacts, "drawdown_path", context="backtest.artifacts"),
        workspace_root=workspace_root,
        context="backtest.artifacts",
        field="drawdown_path",
    )
    trade_csv_abs, _ = _to_workspace_url(
        _require_str(backtest_artifacts, "trade_blotter_path", context="backtest.artifacts"),
        workspace_root=workspace_root,
        context="backtest.artifacts",
        field="trade_blotter_path",
    )
    signal_csv_abs, _ = _to_workspace_url(
        _require_str(backtest_artifacts, "signal_context_path", context="backtest.artifacts"),
        workspace_root=workspace_root,
        context="backtest.artifacts",
        field="signal_context_path",
    )

    analysis = responses["analysis"]
    suggestions = _require_list(analysis, "suggestions", context="analysis")

    trade_blotter = responses["trade_blotter"]
    trades = _require_list(trade_blotter, "trades", context="trade_blotter")
    trade_blotter_artifacts = _require_dict(trade_blotter, "artifacts", context="trade_blotter")

    boundary = responses["boundary"]
    boundary_chart_abs, boundary_url = _to_workspace_url(
        _require_str(boundary, "boundary_chart_path", context="boundary"),
        workspace_root=workspace_root,
        context="boundary",
        field="boundary_chart_path",
    )

    diagnostics_rows: list[list[Any]] = [
        ["mode", "code_strategy", "-", "-", "-"],
        ["signals_count", backtest.get("signals_count", "-"), "-", "-", "-"],
        [
            "preflight_estimated_seconds",
            _require_dict(backtest, "preflight", context="backtest").get("estimated_seconds", "-"),
            "-",
            "-",
            "-",
        ],
    ]

    suggestion_rows: list[list[Any]] = []
    for suggestion in suggestions:
        if not isinstance(suggestion, dict):
            raise ValueError("analysis.suggestions must contain objects")
        suggestion_rows.append(
            [
                suggestion.get("title", "-"),
                suggestion.get("evidence", "-"),
                suggestion.get("confidence", "-"),
                suggestion.get("expected_impact", "-"),
            ]
        )

    trade_rows: list[list[Any]] = []
    for trade in trades:
        if not isinstance(trade, dict):
            raise ValueError("trade_blotter.trades must contain objects")
        trade_rows.append(
            [
                trade.get("symbol", "-"),
                f"{trade.get('entry_ts', '-')} @ {trade.get('entry_price', '-')}",
                f"{trade.get('exit_ts', '-')} @ {trade.get('exit_price', '-')}",
                trade.get("pnl", "-"),
                trade.get("entry_reason", "-"),
                trade.get("exit_reason", "-"),
            ]
        )

    metrics = {
        "Final Equity": _as_float(backtest_metrics.get("final_equity"), context="backtest.metrics", field="final_equity"),
        "Sharpe": _as_float(backtest_metrics.get("sharpe"), context="backtest.metrics", field="sharpe"),
        "Max Drawdown": _as_float(backtest_metrics.get("max_drawdown"), context="backtest.metrics", field="max_drawdown"),
        "CAGR": _as_float(backtest_metrics.get("cagr"), context="backtest.metrics", field="cagr"),
        "Trade Count": int(_as_float(backtest_metrics.get("trade_count"), context="backtest.metrics", field="trade_count")),
        "Signals Count": int(_as_float(backtest.get("signals_count", 0), context="backtest", field="signals_count")),
    }

    diagnostics_table = _render_responsive_table(
        ["Parameter", "Status", "Baseline", "Alternative", "Delta"], diagnostics_rows
    )
    suggestions_table = _render_responsive_table(
        ["Title", "Evidence", "Confidence", "Expected Impact"], suggestion_rows
    )
    trades_table = _render_responsive_table(
        ["Symbol", "Entry", "Exit", "PnL", "Entry Reason", "Exit Reason"], trade_rows
    )

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Fin-Agent Rigorous UI Evidence</title>
<style>
:root {{
  --bg:#0f172a;
  --panel:#111827;
  --panel2:#1f2937;
  --text:#e5e7eb;
  --muted:#94a3b8;
  --ok:#34d399;
  --warn:#f59e0b;
  --bad:#f87171;
  --line:#334155;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; background:linear-gradient(180deg,#0b1020 0%, #111827 60%, #0f172a 100%); color:var(--text); }}
.header {{ padding:20px 24px; border-bottom:1px solid var(--line); background:rgba(17,24,39,.75); position:sticky; top:0; backdrop-filter: blur(4px); z-index:10; }}
.header h1 {{ margin:0; font-size:18px; letter-spacing:.3px; }}
.header .meta {{ margin-top:6px; color:var(--muted); font-size:12px; overflow-wrap:anywhere; }}
.grid {{ display:grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap:12px; padding:16px 24px 10px; }}
.card {{ background:rgba(17,24,39,.9); border:1px solid var(--line); border-radius:10px; padding:12px; }}
.card h2 {{ margin:0 0 8px 0; font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:.6px; }}
.val {{ font-size:30px; font-weight:700; line-height:1.1; }}
.warn {{ color:var(--warn); }}
.bad {{ color:var(--bad); }}
.section {{ margin:10px 24px 16px; background:rgba(17,24,39,.9); border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
.section h3 {{ margin:0; padding:10px 12px; border-bottom:1px solid var(--line); font-size:13px; letter-spacing:.4px; background:rgba(31,41,55,.7); }}
.section .content {{ padding:10px 12px; }}
.chart {{ width:100%; border:1px solid var(--line); border-radius:8px; background:#fff; }}
.two {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; }}
.table-wrap {{ width:100%; }}
.responsive-table {{ width:100%; border-collapse: collapse; font-size:12px; }}
.responsive-table th, .responsive-table td {{ border-bottom:1px solid var(--line); padding:6px; text-align:left; vertical-align:top; white-space:normal; overflow-wrap:anywhere; }}
.responsive-table th {{ color:var(--muted); font-weight:600; }}
.badge {{ display:inline-block; padding:2px 8px; border-radius:999px; border:1px solid var(--line); font-size:11px; }}
.footer {{ padding:8px 24px 20px; color:var(--muted); font-size:11px; overflow-wrap:anywhere; }}
@media (max-width: 1100px) {{
  .grid {{ grid-template-columns:1fr 1fr; }}
  .two {{ grid-template-columns:1fr; }}
}}
@media (max-width: 760px) {{
  .header {{ padding:14px 12px; position:static; }}
  .grid {{ grid-template-columns:1fr 1fr; gap:10px; padding:12px 12px 8px; }}
  .section {{ margin:8px 12px 12px; }}
  .section .content {{ padding:8px; }}
  .footer {{ padding:8px 12px 16px; }}
  .responsive-table thead {{ display:none; }}
  .responsive-table, .responsive-table tbody, .responsive-table tr, .responsive-table td {{ display:block; width:100%; }}
  .responsive-table tr {{ border:1px solid var(--line); border-radius:8px; margin-bottom:8px; background:rgba(15,23,42,.55); }}
  .responsive-table td {{ display:grid; grid-template-columns:minmax(100px,34%) minmax(0,1fr); gap:8px; border-bottom:1px dashed var(--line); padding:7px 8px; }}
  .responsive-table td:last-child {{ border-bottom:none; }}
  .responsive-table td::before {{ content:attr(data-label); color:var(--muted); font-size:10px; text-transform:uppercase; letter-spacing:.5px; font-weight:600; }}
}}
@media (max-width: 480px) {{
  .grid {{ grid-template-columns:1fr; }}
}}
</style>
</head>
<body>
  <div class="header">
    <h1>Fin-Agent Stage 1 Rigorous UI Evidence</h1>
    <div class="meta">Run: {escape(run_dir.name)} | Generated: {escape(generated_at)} | Status: <span class="badge">{escape(str(summary["status"]))}</span></div>
  </div>

  <div class="grid">
    <div class="card"><h2>Final Equity</h2><div class="val">{escape(f"{metrics['Final Equity']:.4f}")}</div></div>
    <div class="card"><h2>Sharpe</h2><div class="val {'bad' if metrics['Sharpe'] < 0 else ''}">{escape(f"{metrics['Sharpe']:.4f}")}</div></div>
    <div class="card"><h2>Max Drawdown</h2><div class="val {'warn' if metrics['Max Drawdown'] < 0 else ''}">{escape(f"{metrics['Max Drawdown']:.4f}")}</div></div>
    <div class="card"><h2>CAGR</h2><div class="val {'warn' if metrics['CAGR'] < 0 else ''}">{escape(f"{metrics['CAGR']:.4f}")}</div></div>
    <div class="card"><h2>Trade Count</h2><div class="val">{escape(str(metrics['Trade Count']))}</div></div>
    <div class="card"><h2>Signals Count</h2><div class="val">{escape(str(metrics['Signals Count']))}</div></div>
  </div>

  <div class="section">
    <h3>Backtest Charts</h3>
    <div class="content two">
      <div>
        <div class="meta" style="margin:0 0 4px 0;color:var(--muted);font-size:12px">Equity Curve</div>
        <img class="chart" src="{escape(equity_url)}" alt="equity curve" />
      </div>
      <div>
        <div class="meta" style="margin:0 0 4px 0;color:var(--muted);font-size:12px">Drawdown</div>
        <img class="chart" src="{escape(drawdown_url)}" alt="drawdown chart" />
      </div>
    </div>
  </div>

  <div class="section">
    <h3>Boundary Visualization</h3>
    <div class="content">
      <img class="chart" src="{escape(boundary_url)}" alt="boundary chart" />
    </div>
  </div>

  <div class="section">
    <h3>Agentic Diagnostics</h3>
    <div class="content">
      {diagnostics_table}
    </div>
  </div>

  <div class="section">
    <h3>Deep Dive Suggestions</h3>
    <div class="content">
      {suggestions_table}
    </div>
  </div>

  <div class="section">
    <h3>Trade Blotter (Top Rows)</h3>
    <div class="content">
      {trades_table}
    </div>
  </div>

  <div class="footer">Artifacts: trade_blotter={escape(_require_str(trade_blotter_artifacts, 'trade_blotter_path', context='trade_blotter.artifacts'))} | signal_context={escape(_require_str(trade_blotter_artifacts, 'signal_context_path', context='trade_blotter.artifacts'))}</div>
</body>
</html>
"""

    dashboard_path = ui_dir / "dashboard.html"
    dashboard_path.write_text(html, encoding="utf-8")

    payload = {
        "run_dir": str(run_dir),
        "summary": summary,
        "paths": {
            "dashboard": str(dashboard_path),
            "equity_svg": equity_abs,
            "equity_url": equity_url,
            "drawdown_svg": drawdown_abs,
            "drawdown_url": drawdown_url,
            "boundary_svg": boundary_chart_abs,
            "boundary_url": boundary_url,
            "trade_blotter_csv": trade_csv_abs,
            "signal_context_csv": signal_csv_abs,
        },
    }

    ui_evidence_path = ui_dir / "ui-evidence.json"
    ui_evidence_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload
