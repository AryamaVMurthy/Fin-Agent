from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class IndiaTaxAssumptions:
    stcg_rate: float = 0.20
    ltcg_rate: float = 0.125
    ltcg_threshold_days: int = 365
    ltcg_exemption_amount: float = 125000.0
    brokerage_bps: float = 3.0
    stt_sell_bps: float = 10.0
    exchange_txn_bps: float = 0.35
    sebi_bps: float = 0.001
    stamp_buy_bps: float = 1.5
    gst_rate: float = 0.18
    apply_cess: bool = True
    cess_rate: float = 0.04
    include_charges: bool = True
    capital_allocation_mode: str = "equal_max_positions"


def _parse_day(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def _holding_days(entry_ts: str, exit_ts: str) -> int:
    return max(0, (_parse_day(exit_ts) - _parse_day(entry_ts)).days)


def _safe_float(value: Any) -> float:
    return float(value) if value is not None and str(value) != "" else 0.0


def _estimate_trade_notional(entry_price: float, strategy: dict[str, Any]) -> float:
    initial_capital = _safe_float(strategy.get("initial_capital"))
    max_positions = max(1, int(strategy.get("max_positions", 1)))
    return initial_capital / float(max_positions)


def compute_tax_report(
    trade_blotter_path: str,
    strategy_payload: dict[str, Any],
    assumptions: IndiaTaxAssumptions,
) -> dict[str, Any]:
    p = Path(trade_blotter_path)
    if not p.exists():
        raise ValueError(f"trade blotter artifact not found: {trade_blotter_path}")

    rows: list[dict[str, str]] = []
    with p.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(dict(row))

    gross_profit = 0.0
    taxable_stcg = 0.0
    taxable_ltcg = 0.0
    total_turnover = 0.0

    for row in rows:
        entry = _safe_float(row.get("entry_price"))
        exit_price = _safe_float(row.get("exit_price"))
        pnl = _safe_float(row.get("pnl"))
        gross_profit += pnl

        notional = _estimate_trade_notional(entry, strategy_payload)
        qty = 0.0 if entry <= 0 else notional / entry
        buy_value = qty * entry
        sell_value = qty * exit_price
        total_turnover += abs(buy_value) + abs(sell_value)

        hold_days = _holding_days(str(row.get("entry_ts", "")), str(row.get("exit_ts", "")))
        if pnl > 0:
            if hold_days >= assumptions.ltcg_threshold_days:
                taxable_ltcg += pnl
            else:
                taxable_stcg += pnl

    brokerage = total_turnover * (assumptions.brokerage_bps / 10000.0)
    stt = total_turnover * (assumptions.stt_sell_bps / 10000.0) * 0.5
    exchange = total_turnover * (assumptions.exchange_txn_bps / 10000.0)
    sebi = total_turnover * (assumptions.sebi_bps / 10000.0)
    stamp = total_turnover * (assumptions.stamp_buy_bps / 10000.0) * 0.5
    gst = (brokerage + exchange) * assumptions.gst_rate

    stcg_tax = taxable_stcg * assumptions.stcg_rate
    taxable_ltcg_after_exemption = max(0.0, taxable_ltcg - assumptions.ltcg_exemption_amount)
    ltcg_tax = taxable_ltcg_after_exemption * assumptions.ltcg_rate
    income_tax_subtotal = stcg_tax + ltcg_tax
    cess = income_tax_subtotal * assumptions.cess_rate if assumptions.apply_cess else 0.0
    charges_total = gst + stt + exchange + sebi + stamp if assumptions.include_charges else 0.0
    total_tax = income_tax_subtotal + cess + charges_total
    net_profit_after_tax = gross_profit - total_tax

    return {
        "metrics_pre_tax": {
            "gross_profit": gross_profit,
            "trade_count": len(rows),
            "taxable_stcg": taxable_stcg,
            "taxable_ltcg": taxable_ltcg,
        },
        "metrics_post_tax": {
            "total_tax": total_tax,
            "net_profit_after_tax": net_profit_after_tax,
        },
        "tax_breakdown": {
            "stcg_tax": stcg_tax,
            "ltcg_tax": ltcg_tax,
            "ltcg_taxable_after_exemption": taxable_ltcg_after_exemption,
            "brokerage": brokerage,
            "stt": stt,
            "exchange": exchange,
            "sebi": sebi,
            "stamp": stamp,
            "gst": gst,
            "cess": cess,
            "income_tax_subtotal": income_tax_subtotal,
            "charges_total": charges_total,
        },
        "assumptions": assumptions.__dict__,
    }
