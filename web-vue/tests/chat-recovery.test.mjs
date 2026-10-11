import assert from 'node:assert/strict'
import test from 'node:test'

import { parseSseChunk } from '../src/api/sse.ts'
import { latestHistoryPage, recoverHistory } from '../src/components/chat/recovery.ts'

function history(overrides = {}) {
  return {
    conversation_id: 'conversation', items: [], total: 0, offset: 0, limit: 100,
    status: 'completed', pending_request_key: null, running: false, active_turn: null,
    retrieval_status: 'not_requested', retrieved_sources: [],
    web_search_status: 'not_requested', web_sources: [], run_error: null,
    ...overrides,
  }
}

test('刷新后恢复已提交的问题和助手草稿', () => {
  const user = { id: 'user-1', role: 'user', content: '怎么退款？' }
  const restored = recoverHistory(history({
    running: true, active_turn: { user_message: user, assistant_text: '先查看订单' },
  }))
  assert.equal(restored.optimistic, user.content)
  assert.equal(restored.streamingText, '先查看订单')
  assert.equal(restored.running, true)
  assert.equal(restored.waiting, false)
})

test('checkpoint 已有当前用户消息时不重复显示乐观消息', () => {
  const user = { id: 'user-1', role: 'user', content: '怎么退款？' }
  const restored = recoverHistory(history({
    items: [user], running: true, active_turn: { user_message: user, assistant_text: '处理中' },
  }))
  assert.deepEqual(restored.messages, [user])
  assert.equal(restored.optimistic, '')
  assert.equal(restored.streamingText, '处理中')
})

test('失败没有新增消息时也按 running=false 清草稿并解除运行锁定', () => {
  const restored = recoverHistory(history({
    run_error: '本轮失败',
    active_turn: { user_message: { id: 'u', role: 'user', content: '问题' }, assistant_text: '残稿' },
  }))
  assert.equal(restored.running, false)
  assert.equal(restored.optimistic, '')
  assert.equal(restored.streamingText, '')
})

test('等待审批按服务端状态恢复，不靠消息条数推断', () => {
  const waiting = recoverHistory(history({ status: 'waiting_approval', pending_request_key: 'r-1' }))
  assert.equal(waiting.waiting, true)
  assert.equal(waiting.waitingRequestKey, 'r-1')
  assert.equal(recoverHistory(history()).waiting, false)
})

test('历史超过 100 条时取最新 100 条', async () => {
  const requests = []
  const page = await latestHistoryPage(async ({ offset, limit }) => {
    requests.push(offset)
    return { total: 235, offset, items: Array.from({ length: limit }, (_, i) => offset + i) }
  })
  assert.deepEqual(requests, [0, 135])
  assert.equal(page.items.at(-1), 234)
})

test('读取历史期间有新回复落库时重新校正最新页偏移', async () => {
  const requests = []
  const page = await latestHistoryPage(async ({ offset }) => {
    requests.push(offset)
    return { total: offset === 0 ? 200 : 202, offset }
  })
  assert.deepEqual(requests, [0, 100, 102])
  assert.equal(page.offset, 102)
})

for (const newline of ['\n', '\r\n', '\r']) {
  test(`SSE 每个字符拆包仍保留事件名和数据 (${JSON.stringify(newline)})`, () => {
    const wire = [': heartbeat', '', 'event: delta', 'data: {"text":"你"}', '',
      'event: error', 'data: {"status":409,"message":"正在回复"}', '', ''].join(newline)
    let carry = ''
    const received = []
    for (const character of wire) {
      const parsed = parseSseChunk(carry + character)
      carry = parsed.carry
      received.push(...parsed.events)
    }
    received.push(...parseSseChunk(carry, true).events)
    assert.deepEqual(received, [
      { event: 'delta', data: '{"text":"你"}' },
      { event: 'error', data: '{"status":409,"message":"正在回复"}' },
    ])
  })
}

test('没有完整空行的事件不提前派发，多行 data 在收尾时正确拼接', () => {
  const wire = 'event: done\ndata: first\ndata: second'
  const incomplete = parseSseChunk(wire)
  assert.deepEqual(incomplete.events, [])
  assert.equal(incomplete.carry, wire)
  assert.deepEqual(parseSseChunk(wire, true).events, [{ event: 'done', data: 'first\nsecond' }])
})
