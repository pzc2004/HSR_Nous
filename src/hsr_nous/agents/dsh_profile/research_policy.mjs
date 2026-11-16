export const name = 'nous-research-policy'
export const inject = ['tools']

const allowedTools = new Set([
  'mcp__nous__submit_claim',
  'mcp__nous__read_investigation',
  'mcp__nous__read_report',
  'mcp__nous__resolve_evidence',
  'mcp__nous__submit_candidate_set',
  'mcp__nous__submit_candidate_proposals',
  'mcp__nous__start_candidate_set',
  'mcp__nous__start_candidate_proposals',
  'mcp__nous__read_candidate_task',
  'mcp__nous__wait_candidate_task',
  'mcp__nous__cancel_candidate_task',
  'mcp__nous__resume_candidate_task',
  'mcp__nous__read_candidate_set_report',
])

export function apply(ctx) {
  ctx.tools.guard((execution) => {
    if (!allowedTools.has(execution.name)) {
      return `tool is outside the research capability allowlist: ${execution.name}`
    }
    return undefined
  })
}
