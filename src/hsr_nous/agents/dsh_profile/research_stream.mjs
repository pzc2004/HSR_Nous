// nous-research-stream：旁路观测 agent/assistant-stream，把 text-delta 帧逐 token
// 回推给聊天桥的 /ingest 端点——ACP 只按整条 committed 消息提交（无 token 流），
// 原生逐字流经此插件补齐。桥不在/端口未注入时全链路静默，绝不影响主会话。
//
// 传输：每会话若干轻量 HTTP POST 到 http://127.0.0.1:<port>/ingest/<sessionId>
// （端口经 HSR_NOUS_STREAM_INGEST_PORT 由 chat_server 注入；dsh.py 的
// _environment 负责透传）。失败静默丢弃——插件只是旁路，丢了就退回
// chunk+打字机降级，不打断 Agent。
export const name = 'nous-research-stream'

export function apply(ctx) {
  const port = process.env.HSR_NOUS_STREAM_INGEST_PORT
  if (!port) return // 独立 dsh 场景（headless/stock web）未注入端口：整插件休眠

  const deliver = (sessionId, payload) => {
    try {
      if (typeof fetch !== 'function') return
      fetch(`http://127.0.0.1:${port}/ingest/${encodeURIComponent(sessionId)}`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload),
      }).catch(() => {}) // 桥不在/已退出：静默丢弃
    } catch {
      // 同步异常同样吞掉——旁路观测绝不上抛
    }
  }

  ctx.on('agent/assistant-stream', ({ agent, frame }) => {
    try {
      if (frame?.type !== 'chunk' || frame.chunk?.type !== 'text-delta') return
      const sessionId = agent?.session?.id
      if (!sessionId) return
      deliver(sessionId, { sessionUpdate: 'agent_message_delta', text: frame.chunk.text })
    } catch {
      // 防御：事件处理绝不让主会话出错
    }
  }, { global: true })
}
