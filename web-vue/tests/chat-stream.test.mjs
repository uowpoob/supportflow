import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'

let server
let streamConversationMessage
const originalFetch = globalThis.fetch

before(async () => {
  server = await createServer({
    root: fileURLToPath(new URL('../', import.meta.url)),
    configFile: false,
    server: { middlewareMode: true, watch: null },
    optimizeDeps: { noDiscovery: true },
  })
  ;({ streamConversationMessage } = await server.ssrLoadModule('/src/api/customer.ts'))
})

after(async () => {
  globalThis.fetch = originalFetch
  await server?.close()
})

test('HTTP 200 流中的 error 事件抛出保留后台状态码的 ApiError', async () => {
  globalThis.fetch = async () => new Response(
    'event: error\ndata: {"status":409,"message":"会话正在回复"}\n\n',
    { headers: { 'Content-Type': 'text/event-stream' } },
  )
  await assert.rejects(async () => {
    for await (const _event of streamConversationMessage('conversation', '问题')) {
      assert.fail('错误事件不应作为成功事件交给页面')
    }
  }, (error) => error.name === 'ApiError' && error.status === 409 && error.message === '会话正在回复')
})

test('fetch 的事件和 JSON 被网络拆包时仍输出正确 delta 与 done', async () => {
  const turn = { conversation_id: 'conversation', messages: [], status: 'completed' }
  const wire = `event: delta\ndata: {"text":"你好"}\n\nevent: done\ndata: ${JSON.stringify(turn)}\n\n`
  const encoder = new TextEncoder()
  globalThis.fetch = async () => new Response(new ReadableStream({
    start(controller) {
      for (const byte of encoder.encode(wire)) controller.enqueue(Uint8Array.of(byte))
      controller.close()
    },
  }))
  const received = []
  for await (const event of streamConversationMessage('conversation', '问题')) received.push(event)
  assert.deepEqual(received, [{ type: 'delta', text: '你好' }, { type: 'done', turn }])
})
