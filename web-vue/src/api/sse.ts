/** SSE 文本解析；不完整的整条事件留在 carry，直到空行边界到达。 */
export interface SseEvent {
  event: string
  data: string
}

interface Pending {
  name: string
  data: string[]
}

export function parseSseChunk(
  buffer: string,
  flush = false,
): { events: SseEvent[]; carry: string } {
  const events: SseEvent[] = []
  let pending: Pending | null = null
  let cursor = 0
  let committed = 0

  const endEvent = (): void => {
    if (pending === null) return
    events.push({ event: pending.name || 'message', data: pending.data.join('\n') })
    pending = null
  }

  while (cursor < buffer.length) {
    const newline = /\r\n|\r|\n/.exec(buffer.slice(cursor))
    if (newline === null && !flush) break
    const end = newline === null ? buffer.length : cursor + newline.index
    // \r 可能只是跨网络包的 \r\n 前半段，收到下一段后再判断。
    if (!flush && buffer[end] === '\r' && end + 1 === buffer.length) break
    const line = buffer.slice(cursor, end)
    cursor = newline === null ? buffer.length : end + newline[0].length

    if (line === '') {
      endEvent()
      committed = cursor
      continue
    }
    if (line.startsWith(':')) continue
    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') {
      pending ??= { name: '', data: [] }
      pending.name = value
    } else if (field === 'data') {
      pending ??= { name: '', data: [] }
      pending.data.push(value)
    }
  }

  if (flush) endEvent()
  return { events, carry: flush ? '' : buffer.slice(committed) }
}
