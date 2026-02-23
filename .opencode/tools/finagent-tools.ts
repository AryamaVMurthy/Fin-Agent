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

export const FinAgentToolsPlugin: Plugin = async () => {
  return {
    tool: {
      "kite_candles_fetch": tool({
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
          return await trackedToolExecute("kite_candles_fetch", args as Record<string, unknown>, async () => postJson("/v1/kite/candles/fetch", {
            ...args,
            persist: args.persist ?? true,
            use_cache: args.use_cache ?? true,
            force_refresh: args.force_refresh ?? false,
          }))
        },
      }),
      "kite_instruments_sync": tool({
        description: "Sync Kite instrument master into local analytics store",
        args: {
          exchange: tool.schema.string().optional(),
          max_rows: tool.schema.number().int().positive().optional(),
        },
        async execute(args) {
          return await trackedToolExecute("kite_instruments_sync", args as Record<string, unknown>, async () => postJson("/v1/kite/instruments/sync", {
            exchange: args.exchange ?? null,
            max_rows: args.max_rows ?? 20000,
          }))
        },
      }),
      "screener_formula_validate": tool({
        description: "Validate custom screener formula",
        args: {
          formula: tool.schema.string(),
        },
        async execute(args) {
          return await trackedToolExecute("screener_formula_validate", args as Record<string, unknown>, async () => postJson("/v1/screener/formula/validate", args))
        },
      }),
      "screener_run": tool({
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
          return await trackedToolExecute("screener_run", args as Record<string, unknown>, async () => postJson("/v1/screener/run", {
            ...args,
            top_k: args.top_k ?? 50,
            sort_order: args.sort_order ?? "desc",
          }))
        },
      }),
      "session_diff": tool({
        description: "Compare the latest two session snapshots and return state changes",
        args: {
          session_id: tool.schema.string(),
        },
        async execute(args) {
          return await trackedToolExecute("session_diff", args as Record<string, unknown>, async () => getJson(`/v1/session/diff${queryString({ session_id: args.session_id })}`))
        },
      }),
      "world_state_build": tool({
        description: "Build point-in-time world state manifest",
        args: {
          universe: tool.schema.array(tool.schema.string()),
          start_date: tool.schema.string(),
          end_date: tool.schema.string(),
          adjustment_policy: tool.schema.string().optional(),
        },
        async execute(args) {
          return await trackedToolExecute("world_state_build", args as Record<string, unknown>, async () => postJson("/v1/world-state/build", {
            ...args,
            adjustment_policy: args.adjustment_policy ?? "none",
          }))
        },
      }),
      "world_state_validate": tool({
        description: "Validate PIT world state for leakage/completeness",
        args: {
          universe: tool.schema.array(tool.schema.string()),
          start_date: tool.schema.string(),
          end_date: tool.schema.string(),
          strict_mode: tool.schema.boolean().optional(),
          adjustment_policy: tool.schema.string().optional(),
        },
        async execute(args) {
          return await trackedToolExecute("world_state_validate", args as Record<string, unknown>, async () => postJson("/v1/world-state/validate-pit", {
            ...args,
            strict_mode: args.strict_mode ?? true,
            adjustment_policy: args.adjustment_policy ?? "none",
          }))
        },
      }),
      "code_strategy_validate": tool({
        description: "Validate agent-generated Python strategy source against required contract",
        args: {
          strategy_name: tool.schema.string().optional(),
          source_code: tool.schema.string(),
        },
        async execute(args) {
          return await trackedToolExecute("code_strategy_validate", args as Record<string, unknown>, async () => postJson("/v1/code-strategy/validate", {
            strategy_name: args.strategy_name ?? null,
            source_code: args.source_code,
          }))
        },
      }),
      "code_strategy_save": tool({
        description: "Save validated agent-generated Python strategy source as a versioned strategy",
        args: {
          strategy_name: tool.schema.string(),
          source_code: tool.schema.string(),
        },
        async execute(args) {
          return await trackedToolExecute("code_strategy_save", args as Record<string, unknown>, async () => postJson("/v1/code-strategy/save", args))
        },
      }),
      "code_strategy_run_sandbox": tool({
        description: "Execute Python strategy source in sandbox for contract/runtime verification",
        args: {
          source_code: tool.schema.string(),
          timeout_seconds: tool.schema.number().int().positive().optional(),
          memory_mb: tool.schema.number().int().positive().optional(),
          cpu_seconds: tool.schema.number().int().positive().optional(),
        },
        async execute(args) {
          return await trackedToolExecute("code_strategy_run_sandbox", args as Record<string, unknown>, async () => postJson("/v1/code-strategy/run-sandbox", {
            source_code: args.source_code,
            timeout_seconds: args.timeout_seconds ?? 5,
            memory_mb: args.memory_mb ?? 256,
            cpu_seconds: args.cpu_seconds ?? 2,
          }))
        },
      }),
      "code_strategy_backtest": tool({
        description: "Backtest an agent-generated Python strategy source end-to-end",
        args: {
          strategy_name: tool.schema.string(),
          source_code: tool.schema.string(),
          universe: tool.schema.array(tool.schema.string()),
          start_date: tool.schema.string(),
          end_date: tool.schema.string(),
          initial_capital: tool.schema.number().positive(),
          timeout_seconds: tool.schema.number().int().positive().optional(),
          memory_mb: tool.schema.number().int().positive().optional(),
          cpu_seconds: tool.schema.number().int().positive().optional(),
        },
        async execute(args) {
          return await trackedToolExecute("code_strategy_backtest", args as Record<string, unknown>, async () => postJson("/v1/code-strategy/backtest", {
            strategy_name: args.strategy_name,
            source_code: args.source_code,
            universe: args.universe,
            start_date: args.start_date,
            end_date: args.end_date,
            initial_capital: args.initial_capital,
            timeout_seconds: args.timeout_seconds ?? 5,
            memory_mb: args.memory_mb ?? 256,
            cpu_seconds: args.cpu_seconds ?? 2,
          }))
        },
      }),
      "code_strategy_analyze": tool({
        description: "Analyze a completed code-strategy backtest and return patch suggestions",
        args: {
          run_id: tool.schema.string(),
          source_code: tool.schema.string(),
          max_suggestions: tool.schema.number().int().positive().optional(),
        },
        async execute(args) {
          return await trackedToolExecute("code_strategy_analyze", args as Record<string, unknown>, async () => postJson("/v1/code-strategy/analyze", {
            run_id: args.run_id,
            source_code: args.source_code,
            max_suggestions: args.max_suggestions ?? 5,
          }))
        },
      }),
      "preflight_custom_code": tool({
        description: "Estimate and enforce runtime budget for code-strategy backtests",
        args: {
          universe: tool.schema.array(tool.schema.string()),
          start_date: tool.schema.string(),
          end_date: tool.schema.string(),
          complexity_multiplier: tool.schema.number().positive().optional(),
          max_allowed_seconds: tool.schema.number().positive().optional(),
        },
        async execute(args) {
          return await trackedToolExecute("preflight_custom_code", args as Record<string, unknown>, async () => postJson("/v1/preflight/custom-code", {
            universe: args.universe,
            start_date: args.start_date,
            end_date: args.end_date,
            complexity_multiplier: args.complexity_multiplier ?? 1.0,
            max_allowed_seconds: args.max_allowed_seconds ?? 30.0,
          }))
        },
      }),
      "backtest_compare": tool({
        description: "Compare baseline and candidate backtest runs",
        args: {
          baseline_run_id: tool.schema.string(),
          candidate_run_id: tool.schema.string(),
        },
        async execute(args) {
          return await trackedToolExecute("backtest_compare", args as Record<string, unknown>, async () => postJson("/v1/backtests/compare", args))
        },
      }),
      "visualize_trade_blotter": tool({
        description: "Return trade blotter and signal context visualization payload",
        args: {
          run_id: tool.schema.string(),
        },
        async execute(args) {
          return await trackedToolExecute("visualize_trade_blotter", args as Record<string, unknown>, async () => postJson("/v1/visualize/trade-blotter", args))
        },
      }),
      "live_feed": tool({
        description: "Fetch live insights feed",
        args: {
          strategy_version_id: tool.schema.string().optional(),
          limit: tool.schema.number().int().positive().optional(),
        },
        async execute(args) {
          return await trackedToolExecute("live_feed", args as Record<string, unknown>, async () => getJson(`/v1/live/feed${queryString({
            strategy_version_id: args.strategy_version_id,
            limit: args.limit ?? 100,
          })}`))
        },
      }),
      "universe_resolve": tool({
        description: "Resolve and normalize universe symbols",
        args: {
          symbols: tool.schema.array(tool.schema.string()),
        },
        async execute(args) {
          return await trackedToolExecute("universe_resolve", args as Record<string, unknown>, async () => postJson("/v1/universe/resolve", args.symbols))
        },
      }),
      "technicals_compute": tool({
        description: "Compute SMA technical features for selected universe and range",
        args: {
          universe: tool.schema.array(tool.schema.string()),
          start_date: tool.schema.string(),
          end_date: tool.schema.string(),
          short_window: tool.schema.number().int().positive().optional(),
          long_window: tool.schema.number().int().positive().optional(),
        },
        async execute(args) {
          return await trackedToolExecute("technicals_compute", args as Record<string, unknown>, async () => postJson("/v1/data/technicals/compute", {
            ...args,
            short_window: args.short_window ?? 5,
            long_window: args.long_window ?? 20,
          }))
        },
      }),
      "backtest_tax_report": tool({
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
          return await trackedToolExecute("backtest_tax_report", args as Record<string, unknown>, async () => postJson("/v1/backtests/tax/report", {
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
      "diagnostics_readiness": tool({
        description: "Read deployment readiness checks for publishable setup",
        args: {},
        async execute(args) {
          return await trackedToolExecute("diagnostics_readiness", args as Record<string, unknown>, async () => getJson("/v1/diagnostics/readiness"))
        },
      }),
      "providers_health": tool({
        description: "Read provider health/configuration summary",
        args: {},
        async execute(args) {
          return await trackedToolExecute("providers_health", args as Record<string, unknown>, async () => getJson("/v1/providers/health"))
        },
      }),
      "session_rehydrate": tool({
        description: "Restore latest persisted session state and recent tool deltas",
        args: {
          session_id: tool.schema.string(),
        },
        async execute(args) {
          return await trackedToolExecute("session_rehydrate", args as Record<string, unknown>, async () => postJson("/v1/session/rehydrate", args))
        },
      }),
      "auth_kite_status": tool({
        description: "Read current Kite connector status",
        args: {},
        async execute() {
          return await getJson("/v1/auth/kite/status")
        },
      }),
    },
  }
}
