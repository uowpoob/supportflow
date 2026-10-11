import type { ConversationMessages, PageQuery } from '../../types'

/** offset=0 是最早一页；用 total 找到最新一页，并校正请求期间新增消息造成的偏移。 */
export async function latestHistoryPage<T extends { total: number; offset: number }>(
  fetchPage: (query: PageQuery) => Promise<T>,
  limit = 100,
): Promise<T> {
  let page = await fetchPage({ offset: 0, limit })
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const offset = Math.max(0, page.total - limit)
    if (offset === page.offset) break
    page = await fetchPage({ offset, limit })
  }
  return page
}

/** 草稿只有在 running 时展示；用户消息已经进入 checkpoint 时按 id 去重。 */
export function recoverHistory(page: ConversationMessages) {
  const active = page.running ? page.active_turn : null
  return {
    messages: [...page.items],
    optimistic: active && !page.items.some((item) => item.id === active.user_message.id)
      ? active.user_message.content : '',
    streamingText: active?.assistant_text ?? '',
    running: page.running,
    waiting: !page.running && page.status === 'waiting_approval',
    waitingRequestKey: page.pending_request_key,
  }
}
