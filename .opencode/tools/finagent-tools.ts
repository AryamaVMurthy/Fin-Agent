import { type Plugin, tool } from "@opencode-ai/plugin"

const API_BASE = process.env.FIN_AGENT_API ?? "http://127.0.0.1:8080"

async function postJson(path: string, body: unknown): Promise<unknown> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  })
  const payload = await response.json()
  if (!response.ok) {
    throw new Error(`finagent_api_error path=${path} status=${response.status} detail=${JSON.stringify(payload)}`)
  }
  return payload
}

async function trackedToolExecute(toolName: string, args: Record<string, unknown>, fn: () => Promise<unknown>): Promise<unknown> {
  const result = await fn()
  const sessionId = typeof args.session_id === "string" ? args.session_id : "default"
  try {
    await postJson("/v1/context/delta", {
      session_id: sessionId,
      tool_name: toolName,
      tool_input: args,
      tool_output: typeof result === "object" && result !== null ? result : { result },
    })
  } catch (error) {
    throw new Error(`context_delta_record_failed tool=${toolName} detail=${String(error)}`)
  }
  return result
}

async function getJson(path: string): Promise<unknown> {
  const response = await fetch(`${API_BASE}${path}`)
  const payload = await response.json()
  if (!response.ok) {
    throw new Error(`finagent_api_error path=${path} status=${response.status} detail=${JSON.stringify(payload)}`)
  }
  return payload
}

function queryString(params: Record<string, unknown>): string {
  const q = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) {
      continue
    }
    q.set(key, String(value))
  }
  const encoded = q.toString()
  return encoded.length > 0 ? `?${encoded}` : ""
}

function parseOptionalJsonObject(input: unknown, fieldName: string): Record<string, unknown> | undefined {
  if (input === undefined || input === null) {
    return undefined
  }
  if (typeof input !== "string") {
    throw new Error(`${fieldName} must be a JSON object string`)
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(input)
  } catch (error) {
    throw new Error(`${fieldName} is not valid JSON: ${String(error)}`)
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error(`${fieldName} must decode to a JSON object`)
  }
  return parsed as Record<string, unknown>
}

export const FinAgentToolsPlugin: Plugin = async () => {
  return {
    tool: {
      "kite.candles.fetch": tool({
        description: "Fetch and optionally persist candle data from Kite",
        args: {
          symbol: tool.schema.string(),
          instrument_token: tool.schema.string(),
          interval: tool.schema.string(),
          from_ts: tool.schema.string(),
          to_ts: tool.schema.string(),
          persist: tool.schema.boolean().optional(),
          use_cache: tool.schema.boolean().optional(),
          force_refresh: tool.schema.boolean().optional(),
        },
        async execute(args) {
          return await trackedToolExecute("kite.candles.fetch", args as Record<string, unknown>, async () => postJson("/v1/kite/candles/fetch", {
            ...args,
            persist: args.persist ?? true,
            use_cache: args.use_cache ?? true,
            force_refresh: args.force_refresh ?? false,
          }))
        },
      }),
      "kite.instruments.sync": tool({
        description: "Sync Kite instrument master into local analytics store",
        args: {
          exchange: tool.schema.string().optional(),
          max_rows: tool.schema.number().int().positive().optional(),
        },
        async execute(args) {
          return await trackedToolExecute("kite.instruments.sync", args as Record<string, unknown>, async () => postJson("/v1/kite/instruments/sync", {
            exchange: args.exchange ?? null,
            max_rows: args.max_rows ?? 20000,
          }))
        },
      }),
      "screener.formula.validate": tool({
        description: "Validate custom screener formula",
        args: {
          formula: tool.schema.string(),
        },
        async execute(args) {
          return await trackedToolExecute("screener.formula.validate", args as Record<string, unknown>, async () => postJson("/v1/screener/formula/validate", args))
        },
      }),
      "screener.run": tool({
        description: "Run custom screener formula against latest market snapshot",
        args: {
          formula: tool.schema.string(),
          as_of: tool.schema.string(),
          universe: tool.schema.array(tool.schema.string()),
          top_k: tool.schema.number().int().positive().optional(),
          rank_by: tool.schema.string().optional(),
          sort_order: tool.schema.string().optional(),
        },
        async execute(args) {
          return await trackedToolExecute("screener.run", args as Record<string, unknown>, async () => postJson("/v1/screener/run", {
            ...args,
            top_k: args.top_k ?? 50,
            sort_order: args.sort_order ?? "desc",
          }))
        },
      }),
      "session.diff": tool({
        description: "Compare the latest two session snapshots and return state changes",
        args: {
          session_id: tool.schema.string(),
        },
        async execute(args) {
          return await trackedToolExecute("session.diff", args as Record<string, unknown>, async () => getJson(`/v1/session/diff${queryString({ session_id: args.session_id })}`))
        },
      }),
      "world-state.build": tool({
        description: "Build point-in-time world state manifest",
        args: {
          universe: tool.schema.array(tool.schema.string()),
          start_date: tool.schema.string(),
          end_date: tool.schema.string(),
          adjustment_policy: tool.schema.string().optional(),
        },
        async execute(args) {
          return await trackedToolExecute("world-state.build", args as Record<string, unknown>, async () => postJson("/v1/world-state/build", {
            ...args,
            adjustment_policy: args.adjustment_policy ?? "none",
          }))
        },
      }),
      "world-state.validate": tool({
        description: "Validate PIT world state for leakage/completeness",
        args: {
          universe: tool.schema.array(tool.schema.string()),
          start_date: tool.schema.string(),
          end_date: tool.schema.string(),
          strict_mode: tool.schema.boolean().optional(),
          adjustment_policy: tool.schema.string().optional(),
        },
        async execute(args) {
          return await trackedToolExecute("world-state.validate", args as Record<string, unknown>, async () => postJson("/v1/world-state/validate-pit", {
            ...args,
            strict_mode: args.strict_mode ?? true,
            adjustment_policy: args.adjustment_policy ?? "none",
          }))
        },
      }),
      "strategy.from-intent": tool({
        description: "Create a strategy version from a saved intent snapshot",
        args: {
          strategy_name: tool.schema.string(),
          intent_snapshot_id: tool.schema.string(),
        },
        async execute(args) {
          return await trackedToolExecute("strategy.from-intent", args as Record<string, unknown>, async () => postJson("/v1/strategy/from-intent", args))
        },
      }),
      "backtest.run": tool({
        description: "Run deterministic backtest from strategy name + intent snapshot",
        args: {
          strategy_name: tool.schema.string(),
          intent_snapshot_id: tool.schema.string(),
        },
        async execute(args) {
          return await trackedToolExecute("backtest.run", args as Record<string, unknown>, async () => postJson("/v1/backtests/run", args))
        },
      }),
      "backtest.compare": tool({
        description: "Compare baseline and candidate backtest runs",
        args: {
          baseline_run_id: tool.schema.string(),
          candidate_run_id: tool.schema.string(),
        },
        async execute(args) {
          return await trackedToolExecute("backtest.compare", args as Record<string, unknown>, async () => postJson("/v1/backtests/compare", args))
        },
      }),
      "tuning.search-space.derive": tool({
        description: "Derive policy-driven tuning search space, layer plan, and dependency graph",
        args: {
          strategy_name: tool.schema.string(),
          intent_snapshot_id: tool.schema.string(),
          optimization_target: tool.schema.string().optional(),
          risk_mode: tool.schema.string().optional(),
          policy_mode: tool.schema.string().optional(),
          include_layers: tool.schema.array(tool.schema.string()).optional(),
          freeze_params_json: tool.schema.string().optional(),
          search_space_overrides_json: tool.schema.string().optional(),
          max_drawdown_limit: tool.schema.number().positive().optional(),
          turnover_cap: tool.schema.number().int().positive().optional(),
        },
        async execute(args) {
          const freezeParams = parseOptionalJsonObject(args.freeze_params_json, "freeze_params_json")
          const searchSpaceOverrides = parseOptionalJsonObject(args.search_space_overrides_json, "search_space_overrides_json")
          return await trackedToolExecute("tuning.search-space.derive", args as Record<string, unknown>, async () => postJson("/v1/tuning/search-space/derive", {
            strategy_name: args.strategy_name,
            intent_snapshot_id: args.intent_snapshot_id,
            optimization_target: args.optimization_target ?? "sharpe",
            risk_mode: args.risk_mode ?? "balanced",
            policy_mode: args.policy_mode ?? "agent_decides",
            include_layers: args.include_layers,
            freeze_params: freezeParams,
            search_space_overrides: searchSpaceOverrides,
            max_drawdown_limit: args.max_drawdown_limit,
            turnover_cap: args.turnover_cap,
          }))
        },
      }),
      "tuning.run": tool({
        description: "Run policy-driven hyperparameter tuning with sensitivity analysis output",
        args: {
          strategy_name: tool.schema.string(),
          intent_snapshot_id: tool.schema.string(),
          optimization_target: tool.schema.string().optional(),
          risk_mode: tool.schema.string().optional(),
          policy_mode: tool.schema.string().optional(),
          include_layers: tool.schema.array(tool.schema.string()).optional(),
          freeze_params_json: tool.schema.string().optional(),
          search_space_overrides_json: tool.schema.string().optional(),
          max_drawdown_limit: tool.schema.number().positive().optional(),
          turnover_cap: tool.schema.number().int().positive().optional(),
          max_trials: tool.schema.number().int().positive().optional(),
          per_trial_estimated_seconds: tool.schema.number().positive().optional(),
        },
        async execute(args) {
          const freezeParams = parseOptionalJsonObject(args.freeze_params_json, "freeze_params_json")
          const searchSpaceOverrides = parseOptionalJsonObject(args.search_space_overrides_json, "search_space_overrides_json")
          return await trackedToolExecute("tuning.run", args as Record<string, unknown>, async () => postJson("/v1/tuning/run", {
            strategy_name: args.strategy_name,
            intent_snapshot_id: args.intent_snapshot_id,
            optimization_target: args.optimization_target ?? "sharpe",
            risk_mode: args.risk_mode ?? "balanced",
            policy_mode: args.policy_mode ?? "agent_decides",
            include_layers: args.include_layers,
            freeze_params: freezeParams,
            search_space_overrides: searchSpaceOverrides,
            max_drawdown_limit: args.max_drawdown_limit,
            turnover_cap: args.turnover_cap,
            max_trials: args.max_trials ?? 20,
            per_trial_estimated_seconds: args.per_trial_estimated_seconds ?? 0.5,
          }))
        },
      }),
      "analysis.deep-dive": tool({
        description: "Generate deep analysis and suggestions from run artifacts",
        args: {
          run_id: tool.schema.string(),
        },
        async execute(args) {
          return await trackedToolExecute("analysis.deep-dive", args as Record<string, unknown>, async () => postJson("/v1/analysis/deep-dive", args))
        },
      }),
      "visualize.trade-blotter": tool({
        description: "Return trade blotter and signal context visualization payload",
        args: {
          run_id: tool.schema.string(),
        },
        async execute(args) {
          return await trackedToolExecute("visualize.trade-blotter", args as Record<string, unknown>, async () => postJson("/v1/visualize/trade-blotter", args))
        },
      }),
      "live.feed": tool({
        description: "Fetch live insights feed",
        args: {
          strategy_version_id: tool.schema.string().optional(),
          limit: tool.schema.number().int().positive().optional(),
        },
        async execute(args) {
          return await trackedToolExecute("live.feed", args as Record<string, unknown>, async () => getJson(`/v1/live/feed${queryString({
            strategy_version_id: args.strategy_version_id,
            limit: args.limit ?? 100,
          })}`))
        },
      }),
      "universe.resolve": tool({
        description: "Resolve and normalize universe symbols",
        args: {
          symbols: tool.schema.array(tool.schema.string()),
        },
        async execute(args) {
          return await trackedToolExecute("universe.resolve", args as Record<string, unknown>, async () => postJson("/v1/universe/resolve", args.symbols))
        },
      }),
      "technicals.compute": tool({
        description: "Compute SMA technical features for selected universe and range",
        args: {
          universe: tool.schema.array(tool.schema.string()),
          start_date: tool.schema.string(),
          end_date: tool.schema.string(),
          short_window: tool.schema.number().int().positive().optional(),
          long_window: tool.schema.number().int().positive().optional(),
        },
        async execute(args) {
          return await trackedToolExecute("technicals.compute", args as Record<string, unknown>, async () => postJson("/v1/data/technicals/compute", {
            ...args,
            short_window: args.short_window ?? 5,
            long_window: args.long_window ?? 20,
          }))
        },
      }),
      "backtest.tax.report": tool({
        description: "Compute optional tax-adjusted report for a completed backtest run",
        args: {
          run_id: tool.schema.string(),
          enabled: tool.schema.boolean().optional(),
          stcg_rate: tool.schema.number().positive().optional(),
          ltcg_rate: tool.schema.number().positive().optional(),
          ltcg_exemption_amount: tool.schema.number().nonnegative().optional(),
          apply_cess: tool.schema.boolean().optional(),
          cess_rate: tool.schema.number().nonnegative().optional(),
          include_charges: tool.schema.boolean().optional(),
        },
        async execute(args) {
          return await trackedToolExecute("backtest.tax.report", args as Record<string, unknown>, async () => postJson("/v1/backtests/tax/report", {
            run_id: args.run_id,
            enabled: args.enabled ?? true,
            stcg_rate: args.stcg_rate ?? 0.20,
            ltcg_rate: args.ltcg_rate ?? 0.125,
            ltcg_exemption_amount: args.ltcg_exemption_amount ?? 125000.0,
            apply_cess: args.apply_cess ?? true,
            cess_rate: args.cess_rate ?? 0.04,
            include_charges: args.include_charges ?? true,
          }))
        },
      }),
      "diagnostics.readiness": tool({
        description: "Read deployment readiness checks for publishable setup",
        args: {},
        async execute(args) {
          return await trackedToolExecute("diagnostics.readiness", args as Record<string, unknown>, async () => getJson("/v1/diagnostics/readiness"))
        },
      }),
      "providers.health": tool({
        description: "Read provider health/configuration summary",
        args: {},
        async execute(args) {
          return await trackedToolExecute("providers.health", args as Record<string, unknown>, async () => getJson("/v1/providers/health"))
        },
      }),
      "session.rehydrate": tool({
        description: "Restore latest persisted session state and recent tool deltas",
        args: {
          session_id: tool.schema.string(),
        },
        async execute(args) {
          return await trackedToolExecute("session.rehydrate", args as Record<string, unknown>, async () => postJson("/v1/session/rehydrate", args))
        },
      }),
      "auth.kite.status": tool({
        description: "Read current Kite connector status",
        args: {},
        async execute() {
          return await getJson("/v1/auth/kite/status")
        },
      }),
    },
  }
}
