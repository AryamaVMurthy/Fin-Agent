import React from "react";

const metricCards = [
  { label: "Final Equity", value: "--" },
  { label: "Sharpe", value: "--" },
  { label: "Max Drawdown", value: "--" },
  { label: "CAGR", value: "--" },
];

export default function App() {
  return (
    <main className="app-shell">
      <header className="hero">
        <h1>Fin-Agent Stage 1</h1>
        <p>Chat-centric strategy workspace powered by OpenCode + Fin-Agent tools.</p>
      </header>
      <section className="metrics-grid">
        {metricCards.map((metric) => (
          <article className="metric-card" key={metric.label}>
            <span className="metric-label">{metric.label}</span>
            <strong className="metric-value">{metric.value}</strong>
          </article>
        ))}
      </section>
      <section className="placeholder">
        <h2>Web UI scaffold ready</h2>
        <p>
          Next tasks wire live chat, runs history, tuning analytics, and visualization panels on top of
          `/v1/*` APIs.
        </p>
      </section>
    </main>
  );
}
