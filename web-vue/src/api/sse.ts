/**
 * 极小的 SSE 解析器（只做解析，不认业务事件名）。
 *
 * 为什么不直接用浏览器自带的 `EventSource`：
 * `EventSource` **只能发 GET，带不了请求体**。后端的流式接口是
 * `POST /customer/conversations/{id}/messages/stream`，要在 body 里放 `{content}`，
 * 所以只能自己 fetch + 自己按 SSE 格式拆。
 *
 * SSE 的报文长这样（`\n` 或 `\r\n` 都算换行）：
 *
 *     event: delta
 *     data: {"text": "你"}
 *
 *     event: done
 *     data: {"conversation_id": "...", ...}
 *
 * 约定：**一个空行代表一条事件结束**；同名多行 `data:` 用换行拼起来。
 */

export interface SseEvent {
  /** `event:` 那行；没写就是 'message' */
  event: string
  /** `data:` 那行（多行会拼在一起）；没写就是 '' */
  data: string
}

/** 三种换行都算 —— 服务端用哪种都合法。 */
const NEWLINE = /\r\n|\r|\n/

/** 一条事件（累积中的）。 */
interface Pending {
  name: string
  data: string[]
}

/**
 * 把一段 SSE 文本拆成事件列表。
 *
 * `flush=true` 表示"这是最后一段了"：末尾没有空行时也把剩下的一行当作完整事件。
 * 中途调用（flush=false）时末尾那行可能只收了一半，不能解析 —— 所以它会
 * **以字符串的形式还给你**（`carry`），下次和新的数据拼起来再解。
 */
export function parseSseChunk(
  buffer: string,
  flush = false,
): { events: SseEvent[]; carry: string } {
  const lines = buffer.split(NEWLINE)
  // 最后一项是"还没收到换行"的半行：留着下次再拼（除非已确认是最后一段）。
  let carry = ''
  if (!flush) {
    carry = lines.pop() ?? ''
  }

  const events: SseEvent[] = []
  let pending: Pending | null = null

  const endEvent = (): void => {
    if (pending === null) return
    events.push({
      event: pending.name === '' ? 'message' : pending.name,
      data: pending.data.join('\n'),
    })
    pending = null
  }

  for (const line of lines) {
    // 空行 = 一条事件结束。
    if (line === '') {
      endEvent()
      continue
    }
    // 以冒号开头的是注释（心跳常见），整行丢掉。
    if (line.startsWith(':')) continue

    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    // 规范：冒号后面紧跟的一个空格不算内容的一部分。
    let value = colon === -1 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)

    if (field === 'event') {
      pending ??= { name: '', data: [] }
      pending.name = value
    } else if (field === 'data') {
      pending ??= { name: '', data: [] }
      pending.data.push(value)
    }
    // `id:` / `retry:` 这里用不上，忽略。
  }

  endEvent()
  return { events, carry }
}
