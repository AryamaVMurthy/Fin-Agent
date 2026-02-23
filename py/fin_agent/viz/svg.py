from __future__ import annotations

from pathlib import Path


def _scale(values: list[float], low: float, high: float) -> list[float]:
    min_v = min(values)
    max_v = max(values)
    if max_v == min_v:
        return [((low + high) / 2.0) for _ in values]
    return [high - ((value - min_v) / (max_v - min_v)) * (high - low) for value in values]


def write_line_chart_svg(path: Path, title: str, x_labels: list[str], y_values: list[float]) -> None:
    if not x_labels or not y_values or len(x_labels) != len(y_values):
        raise ValueError("invalid chart data")

    width = 960
    height = 420
    margin = 40
    chart_left = margin
    chart_right = width - margin
    chart_top = 70
    chart_bottom = height - margin

    points_x = []
    count = len(y_values)
    for idx in range(count):
        if count == 1:
            points_x.append((chart_left + chart_right) / 2.0)
        else:
            points_x.append(chart_left + idx * ((chart_right - chart_left) / (count - 1)))
    points_y = _scale(y_values, chart_top, chart_bottom)

    polyline = " ".join(f"{x:.2f},{y:.2f}" for x, y in zip(points_x, points_y))
    last_value = y_values[-1]
    last_label = x_labels[-1]

    svg = f"""<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{width}\" height=\"{height}\" viewBox=\"0 0 {width} {height}\">
  <rect x=\"0\" y=\"0\" width=\"{width}\" height=\"{height}\" fill=\"#0f172a\"/>
  <text x=\"{margin}\" y=\"36\" fill=\"#e2e8f0\" font-size=\"22\" font-family=\"monospace\">{title}</text>
  <line x1=\"{chart_left}\" y1=\"{chart_bottom}\" x2=\"{chart_right}\" y2=\"{chart_bottom}\" stroke=\"#334155\" stroke-width=\"1\"/>
  <line x1=\"{chart_left}\" y1=\"{chart_top}\" x2=\"{chart_left}\" y2=\"{chart_bottom}\" stroke=\"#334155\" stroke-width=\"1\"/>
  <polyline points=\"{polyline}\" fill=\"none\" stroke=\"#22d3ee\" stroke-width=\"2\"/>
  <circle cx=\"{points_x[-1]:.2f}\" cy=\"{points_y[-1]:.2f}\" r=\"4\" fill=\"#f59e0b\"/>
  <text x=\"{margin}\" y=\"{height - 12}\" fill=\"#94a3b8\" font-size=\"12\" font-family=\"monospace\">last={last_label} value={last_value:.4f}</text>
</svg>
"""
    path.write_text(svg, encoding="utf-8")
