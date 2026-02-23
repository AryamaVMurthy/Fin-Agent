import type { Plugin } from "@opencode-ai/plugin"

export const FinAgentOrchestratorPlugin: Plugin = async () => {
  const apiBase = process.env.FIN_AGENT_API ?? "http://127.0.0.1:8080"

  async function persistSnapshot(sessionId: string, state: Record<string, unknown>): Promise<void> {
    const response = await fetch(`${apiBase}/v1/session/snapshot`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, state }),
    })
    if (!response.ok) {
      const payload = await response.text()
      throw new Error(`session_snapshot_failed status=${response.status} detail=${payload}`)
    }
  }

  return {
    "tool.execute.before": async (input, output) => {
      if (!input.tool.startsWith("kite.") && !input.tool.startsWith("screener.")) {
        return
      }
      output.args = {
        ...output.args,
      }
    },
    "tool.execute.after": async (input) => {
      if (input.tool.startsWith("kite.") || input.tool.startsWith("screener.")) {
        console.log(`[finagent-tool] executed tool=${input.tool}`)
      }
    },
    "experimental.session.compacting": async (_input, output) => {
      const finContext = `\n## Fin-Agent Persistent Context\n- Preserve latest strategy assumptions\n- Preserve latest provider sync states\n- Preserve most recent screener formula and as_of date\n`
      output.context.push(finContext)
      await persistSnapshot("default", {
        compaction_context: finContext,
        context_size: output.context.length,
        compacted_at: new Date().toISOString(),
      })
    },
  }
}
