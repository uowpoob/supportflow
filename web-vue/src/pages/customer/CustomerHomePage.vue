<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'

import {
  createConversation,
  deleteConversation,
  fetchConversationMessages,
  fetchConversations,
  streamConversationMessage,
} from '../../api/customer'
import { ApiError } from '../../api/client'
import { useAuth } from '../../auth/useAuth'
import ChatThread from '../../components/chat/ChatThread.vue'
import ConversationList from '../../components/chat/ConversationList.vue'
import RetrievedSources from '../../components/chat/RetrievedSources.vue'
import { latestHistoryPage, recoverHistory } from '../../components/chat/recovery'
import AppIcon from '../../components/common/AppIcon.vue'
import ErrorAlert from '../../components/common/ErrorAlert.vue'
import LoadingLine from '../../components/common/LoadingLine.vue'
import { useApi, type AsyncState } from '../../composables/useApi'
import type {
  ChatMessage, ConversationMessages, MessageTurn, RetrievalStatus, RetrievedSource,
  WebSearchStatus, WebSource,
} from '../../types'

const { user } = useAuth()
const selectedId = ref<string | null>(null)
const messages = ref<ChatMessage[]>([])
const draft = ref('')
// 本页的 SSE 与恢复后的后台运行分别管理，避免轮询覆盖实时增量。
const sending = ref(false)
const creating = ref(false)
const optimistic = ref('')
const streamingText = ref('')
const sendError = ref('')
const turnStatus = ref<RetrievalStatus | null>(null)
const turnSources = ref<RetrievedSource[]>([])
const webSearchStatus = ref<WebSearchStatus>('not_requested')
const webSources = ref<WebSource[]>([])
const waiting = ref(false)
const waitingRequestKey = ref<string | null>(null)
const waitingIds = ref<string[]>([])
const runningElsewhere = ref(false)
const recoveringConnection = ref(false)
const showRunning = computed(() => runningElsewhere.value && !waiting.value && !sending.value)
const selectionRestored = ref(false)
const messageState = ref<AsyncState>('done')
const messageError = ref('')
const deletingId = ref<string | null>(null)

let disposed = false
let historyVersion = 0
let sendVersion = 0
let inFlight: AbortController | null = null
let poller: ReturnType<typeof setTimeout> | null = null
let interruptedTurn: { content: string; previousIds: Set<string>; error: string } | null = null

function selectionKey(userId: number): string {
  return `supportflow:selected-conversation:${userId}`
}

function savedSelection(userId: number): string | null {
  try { return localStorage.getItem(selectionKey(userId)) } catch { return null }
}

function persistSelection(id: string | null): void {
  const userId = user.value?.id
  if (userId === undefined) return
  try {
    if (id === null) localStorage.removeItem(selectionKey(userId))
    else localStorage.setItem(selectionKey(userId), id)
  } catch { /* 禁止浏览器存储时仍可正常使用聊天。 */ }
}

// 只恢复当前账号列表中的 id；较旧的选中会话可能不在第一批 50 条里。
const { state: listState, data: listPage, error: listError, reload: reloadList } = useApi(async () => {
  const userId = user.value?.id
  const saved = userId === undefined ? null : savedSelection(userId)
  const first = await fetchConversations({ limit: 50 })
  if (saved === null || first.items.some((item) => item.id === saved)) return first
  let offset = first.items.length
  while (offset < first.total) {
    const page = await fetchConversations({ offset, limit: 100 })
    const found = page.items.find((item) => item.id === saved)
    if (found) return { ...first, items: [...first.items, found] }
    if (page.items.length === 0) break
    offset += page.items.length
  }
  return first
})
const conversations = computed(() => listPage.value?.items ?? [])

watch([listState, listPage], () => {
  if (selectionRestored.value || listState.value !== 'done' || listPage.value === null) return
  const userId = user.value?.id
  if (userId === undefined) return
  const saved = savedSelection(userId)
  if (saved !== null && conversations.value.some((item) => item.id === saved)) {
    selectedId.value = saved
  } else if (saved !== null) {
    persistSelection(null)
  }
  selectionRestored.value = true
})

watch(selectedId, () => {
  persistSelection(selectedId.value)
  void reloadMessages()
})

function rememberWaiting(id: string, active: boolean): void {
  const rest = waitingIds.value.filter((item) => item !== id)
  waitingIds.value = active ? [...rest, id] : rest
}

function applyServerStatus(page: ConversationMessages): void {
  const recovered = recoverHistory(page)
  messages.value = recovered.messages
  optimistic.value = recovered.optimistic
  streamingText.value = recovered.streamingText
  runningElsewhere.value = recovered.running
  waiting.value = recovered.waiting
  waitingRequestKey.value = recovered.waiting ? recovered.waitingRequestKey : null
  rememberWaiting(page.conversation_id, recovered.waiting)
  turnStatus.value = page.retrieval_status
  turnSources.value = page.retrieved_sources
  webSearchStatus.value = page.web_search_status
  webSources.value = page.web_sources
  if (page.run_error) sendError.value = page.run_error
  else if (page.running) sendError.value = ''
  else if (interruptedTurn !== null) {
    const interrupted = interruptedTurn
    const userIndex = page.items.findIndex((item) => item.role === 'user'
      && item.content === interrupted.content && !interrupted.previousIds.has(item.id))
    const answered = userIndex !== -1
      && (page.items.slice(userIndex + 1).some((item) => item.role === 'assistant') || recovered.waiting)
    if (answered) sendError.value = ''
    else if (userIndex === -1) {
      draft.value = interruptedTurn.content
      sendError.value = interruptedTurn.error === '回复连接中断，正在读取后台运行状态'
        ? '回复连接中断，未确认本轮结果，请查看历史后再决定是否重发'
        : interruptedTurn.error
    }
  }
  if (!page.running) interruptedTurn = null
  recoveringConnection.value = false
}

// 初次加载可显示骨架屏；轮询失败保留已有内容与锁定状态，并自动重试。
async function loadMessages(background: boolean): Promise<void> {
  const target = selectedId.value
  if (disposed || sending.value || target === null) return
  stopPolling()
  const version = ++historyVersion
  if (!background) messageState.value = 'loading'
  messageError.value = ''
  try {
    const page = await latestHistoryPage((query) => fetchConversationMessages(target, query))
    if (disposed || version !== historyVersion || selectedId.value !== target || sending.value) return
    applyServerStatus(page)
    messageState.value = 'done'
  } catch (error) {
    if (disposed || version !== historyVersion || selectedId.value !== target || sending.value) return
    messageError.value = error instanceof ApiError ? error.message : '历史消息读取失败，请重试'
    if (!background) messageState.value = 'error'
  } finally {
    if (!disposed && version === historyVersion && selectedId.value === target) syncPolling()
  }
}

async function reloadMessages(): Promise<void> {
  await loadMessages(false)
}

function stopPolling(): void {
  if (poller !== null) clearTimeout(poller)
  poller = null
}

function syncPolling(): void {
  stopPolling()
  if (disposed || sending.value || selectedId.value === null
    || (!waiting.value && !runningElsewhere.value && !recoveringConnection.value)) return
  // 一次请求完成后再排下一次，慢请求不会与下一次轮询重叠。
  poller = setTimeout(() => {
    poller = null
    void loadMessages(true)
  }, runningElsewhere.value || recoveringConnection.value ? 2000 : 4000)
}

// 取消浏览器读取不会取消服务器上的图，回到会话后由历史快照继续恢复。
function cancelStream(): void {
  sendVersion += 1
  inFlight?.abort()
  inFlight = null
  sending.value = false
  creating.value = false
}

function clearTurnState(): void {
  historyVersion += 1
  cancelStream()
  stopPolling()
  messages.value = []
  optimistic.value = ''
  streamingText.value = ''
  turnStatus.value = null
  turnSources.value = []
  webSearchStatus.value = 'not_requested'
  webSources.value = []
  sendError.value = ''
  messageError.value = ''
  messageState.value = 'done'
  waiting.value = false
  waitingRequestKey.value = null
  runningElsewhere.value = false
  recoveringConnection.value = false
  interruptedTurn = null
}

onUnmounted(() => {
  disposed = true
  historyVersion += 1
  stopPolling()
  cancelStream()
})

const canSend = computed(() => draft.value.trim() !== '' && selectionRestored.value
  && !sending.value && !creating.value && !waiting.value && !runningElsewhere.value && !recoveringConnection.value
  && (selectedId.value === null || messageState.value === 'done'))
const loadingMessages = computed(() => messageState.value === 'loading' && !sending.value)
const inputPlaceholder = computed(() => {
  if (waiting.value) return '正在等待管理员审批，这一轮结束前不能发新消息'
  if (runningElsewhere.value) return '上一条还在回复中，等它结束再发下一条'
  if (recoveringConnection.value) return '正在确认后台运行状态，请稍候'
  return '问点什么，比如「索尼 WH-1000XM5 怎么用有线模式」'
})

function applyTurn(target: string, turn: MessageTurn): void {
  if (selectedId.value !== target) return
  const seen = new Set(messages.value.map((message) => message.id))
  for (const message of turn.messages) {
    if (seen.has(message.id)) continue
    seen.add(message.id)
    messages.value.push(message)
  }
  optimistic.value = ''
  streamingText.value = ''
  runningElsewhere.value = false
  waiting.value = turn.status === 'waiting_approval'
  waitingRequestKey.value = waiting.value ? turn.pending_request_key : null
  rememberWaiting(target, waiting.value)
  turnStatus.value = turn.retrieval_status
  turnSources.value = turn.retrieved_sources
  webSearchStatus.value = turn.web_search_status
  webSources.value = turn.web_sources
  messageState.value = 'done'
  if (turn.title && listPage.value !== null) {
    const title = turn.title
    listPage.value = { ...listPage.value, items: listPage.value.items.map((item) =>
      item.id === target ? { ...item, title } : item) }
  }
}

async function send(): Promise<void> {
  if (!canSend.value) return
  const content = draft.value.trim()
  const previousIds = new Set(messages.value.map((item) => item.id))
  const version = ++sendVersion
  historyVersion += 1
  stopPolling()
  sending.value = true
  sendError.value = ''
  turnStatus.value = null
  turnSources.value = []
  webSearchStatus.value = 'not_requested'
  webSources.value = []
  streamingText.value = ''
  optimistic.value = content
  draft.value = ''
  let target = selectedId.value
  let completed = false

  try {
    if (target === null) {
      creating.value = true
      const created = await createConversation()
      if (disposed || version !== sendVersion) return
      target = created.id
      selectedId.value = target
      persistSelection(target)
      reloadList()
      creating.value = false
    }
    const controller = new AbortController()
    inFlight = controller
    let turn: MessageTurn | null = null
    for await (const event of streamConversationMessage(target, content, controller.signal)) {
      if (disposed || version !== sendVersion || selectedId.value !== target) return
      if (event.type === 'delta') streamingText.value += event.text
      else if (event.type === 'done') turn = event.turn
    }
    if (turn === null) throw new ApiError(0, '回复连接中断，正在读取后台运行状态')
    applyTurn(target, turn)
    completed = true
  } catch (error) {
    if (disposed || version !== sendVersion || selectedId.value !== target) return
    if (!(error instanceof DOMException && error.name === 'AbortError')) {
      sendError.value = error instanceof ApiError ? error.message : '消息发送失败'
      // 不自动重发；工具可能已产生结果。409 的具体状态由历史接口确认。
      recoveringConnection.value = target !== null
      if (error instanceof ApiError && error.status === 409) {
        draft.value = content
        sendError.value = ''
      } else if (target === null) {
        draft.value = content
      } else {
        interruptedTurn = { content, previousIds, error: sendError.value }
      }
    }
  } finally {
    if (!disposed && version === sendVersion) {
      creating.value = false
      sending.value = false
      inFlight = null
      if (completed || target === null) {
        optimistic.value = ''
        streamingText.value = ''
      }
      // done、错误事件、网络断流都立刻核对历史；running=false 即可解锁，无需等消息增加。
      if (target !== null && selectedId.value === target) await loadMessages(true)
      syncPolling()
      reloadList()
    }
  }
}

function selectConversation(id: string): void {
  if (id === selectedId.value) return
  clearTurnState()
  selectedId.value = id
}

async function removeConversation(id: string): Promise<void> {
  if (deletingId.value !== null) return
  if (!window.confirm('确定删除这个会话吗？对话记录和它关联的退款申请会一起删除，且无法恢复。')) return
  deletingId.value = id
  try {
    await deleteConversation(id)
    if (selectedId.value === id) {
      clearTurnState()
      selectedId.value = null
    }
    rememberWaiting(id, false)
    reloadList()
  } catch (error) {
    sendError.value = error instanceof ApiError ? error.message : '删除失败，请重试'
  } finally {
    deletingId.value = null
  }
}
</script>

<template>
  <div class="stack customer-home">
    <header class="page-head">
      <div class="eyebrow">CUSTOMER WORKSPACE</div>
      <h2 class="page-head__title">你好，{{ user?.username }} <span class="greeting-dot" aria-hidden="true">✦</span></h2>
      <p class="page-head__desc">售后事务，在这里轻松解决。</p>
    </header>

    <div class="card-grid">
      <RouterLink class="entry-card entry-card--blue" to="/customer/orders">
        <span class="entry-card__icon"><AppIcon name="box" :size="20" /></span>
        <span class="entry-card__title">我的订单</span>
        <span class="entry-card__desc">查看订单详情与退款资格</span>
        <span class="entry-card__arrow" aria-hidden="true">↗</span>
      </RouterLink>
      <RouterLink class="entry-card entry-card--amber" to="/customer/refund-requests">
        <span class="entry-card__icon"><AppIcon name="receipt" :size="20" /></span>
        <span class="entry-card__title">我的退款申请</span>
        <span class="entry-card__desc">查看申请进度与审批意见</span>
        <span class="entry-card__arrow" aria-hidden="true">↗</span>
      </RouterLink>
    </div>

    <div class="chat-layout">
      <aside class="chat-layout__side">
        <div class="side-head">
          <span class="side-head__label"><AppIcon name="chat" :size="16" />历史会话</span>
          <span class="side-count">{{ conversations.length }}</span>
        </div>

        <div v-if="listState === 'loading'" class="pane-pad">
          <LoadingLine />
        </div>

        <div v-else-if="listState === 'error'" class="side-empty">
          <p class="muted">{{ listError }}</p>
          <button type="button" class="btn btn--ghost btn--sm" @click="reloadList">重试</button>
        </div>

        <ConversationList
          v-else
          :items="conversations"
          :selected-id="selectedId"
          :disabled="sending || deletingId !== null"
          :waiting-ids="waitingIds"
          @select="selectConversation"
          @remove="removeConversation"
        />
      </aside>

      <section class="chat-layout__main">
        <div class="chat-head">
          <span class="chat-head__avatar"><AppIcon name="robot" :size="21" /></span>
          <div><strong>SupportFlow 助手</strong><span>订单 · 政策 · 退款</span></div>
          <span class="chat-head__badge">智能售后</span>
        </div>
        <!-- 还没选中会话也直接给一个空聊天区（像 ChatGPT 那样：进来就能打字，
             不用先点左边列表）。发送时 `send` 会先建一个会话、再把这句发进去。 -->
        <ChatThread
          v-if="selectedId === null"
          :messages="messages"
          :pending="sending"
          :optimistic="optimistic"
          :streaming="streamingText"
          :running-elsewhere="showRunning"
          @suggest="draft = $event"
        />

        <div v-else-if="loadingMessages" class="pane-pad">
          <LoadingLine />
        </div>

        <div v-else-if="messageState === 'error'" class="chat-empty">
          <p class="muted">{{ messageError }}</p>
          <button type="button" class="btn btn--ghost btn--sm" @click="reloadMessages">
            重试
          </button>
        </div>

        <ChatThread
          v-else
          :messages="messages"
          :pending="sending"
          :optimistic="optimistic"
          :streaming="streamingText"
          :running-elsewhere="showRunning"
          @suggest="draft = $event"
        />

        <RetrievedSources
          v-if="turnStatus && (turnStatus !== 'not_requested' || webSearchStatus !== 'not_requested')"
          :status="turnStatus"
          :sources="turnSources"
          :web-status="webSearchStatus"
          :web-sources="webSources"
        />

        <div v-if="sendError" class="pane-pad">
          <ErrorAlert :message="sendError" />
        </div>

        <div v-if="messageError && messageState !== 'error'" class="pane-pad">
          <ErrorAlert :message="messageError" />
        </div>

        <!-- 会话被暂停：Agent 已提交退款申请，图停在那里等管理员决策。
             这期间输入框必须锁上 —— 后端会返回 409，按钮能点就是骗人。 -->
        <div v-if="waiting" class="pane-pad">
          <div class="alert alert--warn alert--row">
            <span>
              这个会话已暂停，正在等待管理员审批（申请编号
              {{ waitingRequestKey ?? '见「我的退款申请」' }}）。
              批准或拒绝之后，结果会自动出现在上面的对话里。
            </span>
            <button type="button" class="btn btn--ghost btn--sm" @click="reloadMessages">
              刷新
            </button>
          </div>
        </div>

        <div v-else-if="showRunning" class="pane-pad">
          <div class="alert alert--info alert--row">
            <span>
              上一条消息仍在后台回复，已恢复当前进度。
              回复内容会自动更新，完成后可以继续提问。
            </span>
            <button type="button" class="btn btn--ghost btn--sm" @click="reloadMessages">
              刷新
            </button>
          </div>
        </div>

        <!-- 输入框永远在这里：没选会话也能打字，发送时先把会话建出来。
             ⚠️ 一轮没跑完之前不让切会话（列表 `:disabled="sending"`）：
             结果要贴回发起时那个会话，切了就对不上；后端同一个会话也会返回 409。 -->
        <form class="composer" @submit.prevent="send">
          <input
            v-model="draft"
            class="composer__input"
            aria-label="售后咨询问题"
            :disabled="sending || waiting || runningElsewhere || recoveringConnection || !selectionRestored || loadingMessages"
            :placeholder="inputPlaceholder"
          />
          <button type="submit" class="btn btn--primary btn--icon" :disabled="!canSend">
            <AppIcon name="send" :size="15" />
            <span>{{ sending ? (creating ? '创建中…' : '回复中…') : '发送' }}</span>
          </button>
        </form>
        <div class="composer-note">回复仅供参考，退款资格与处理结果以实际订单和审批记录为准。</div>
      </section>
    </div>
  </div>
</template>
