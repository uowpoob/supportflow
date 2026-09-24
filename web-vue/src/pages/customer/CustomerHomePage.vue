<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'

import {
  createConversation,
  fetchConversationMessages,
  fetchConversations,
  streamConversationMessage,
} from '../../api/customer'
import { ApiError } from '../../api/client'
import { useAuth } from '../../auth/useAuth'
import ChatThread from '../../components/chat/ChatThread.vue'
import ConversationList from '../../components/chat/ConversationList.vue'
import RetrievedSources from '../../components/chat/RetrievedSources.vue'
import ErrorAlert from '../../components/common/ErrorAlert.vue'
import LoadingLine from '../../components/common/LoadingLine.vue'
import { useApi } from '../../composables/useApi'
import PlaceholderBlock from '../../layouts/PlaceholderBlock.vue'
import type { ChatMessage, MessageTurn, RetrievalStatus, RetrievedSource } from '../../types'

/**
 * 客户首页：快捷入口 + 左侧会话列表 + 右侧对话区。
 *
 * 数据分三块，各自独立：
 * - 会话列表：`GET /customer/conversations`
 * - 历史消息：`GET /customer/conversations/{id}/messages`（选中哪个拉哪个）
 * - 发消息：  `POST /customer/conversations/{id}/messages/stream`（流式，吐一个字显示一个字）
 *
 * 发消息只走流式这一条路。非流式接口（不带 `/stream`）后端还留着，
 * 但前端不用它 —— 两个接口返回的结构完全一样，留两条路只是多一份要维护的分支。
 */
const { user } = useAuth()

// ------------------------- 状态 -------------------------

/** 当前选中的会话；null = 还没选，右侧显示引导。 */
const selectedId = ref<string | null>(null)

/** 界面上渲染的消息 = 历史 + 本轮新增。 */
const messages = ref<ChatMessage[]>([])

const draft = ref('')
/** 一轮请求正在跑（非流式接口要等整轮，界面得自己撑住这段时间）。 */
const sending = ref(false)
/** 刚发出去、还没等到服务端确认的那句话，先显示出来。 */
const optimistic = ref('')
/**
 * 流式进行中的助手文字，逐字增长。
 *
 * 它**不进 `messages`**：`messages` 里的是"服务端已经存好的消息"，
 * 而这段字只是屏幕上的草稿。等服务端把 `done` 发回来，草稿整段丢掉、
 * 换成正式消息 —— 这样就不会出现"模型说的话"和"库里的话"两套内容对不上。
 */
const streamingText = ref('')
const sendError = ref('')

/** 本轮的检索状态与依据 —— 属于"这一轮"，不混进消息列表。 */
const turnStatus = ref<RetrievalStatus | null>(null)
const turnSources = ref<RetrievedSource[]>([])

const creating = ref(false)

/**
 * 会话被"暂停"在图里等管理员审批 —— 这是后端 `wait_for_approval` 节点的中断态。
 *
 * 三条约定（都跟后端契约绑定，别自己加戏）：
 * - 暂停期间**发消息一定被后端 409 挡回来**，所以输入框必须锁上，别让用户白点。
 * - 审批完成后由**服务端**往这条会话追加一条回复，前端只是把它读回来：
 *   接口没有推送，只能隔几秒问一次历史接口。
 * - 刷新页面会丢掉"正在等待"这个界面状态（历史接口不返回它），
 *   这时靠"发一条被 409 挡回来"重新认出来。
 */
const waiting = ref(false)
/** 暂停中的那张申请编号；靠 409 反推出来的那次拿不到编号，为 null。 */
const waitingRequestKey = ref<string | null>(null)
/** 开始等待那一刻已有多少条消息 —— 审批结果一到，条数就比它多。 */
let waitingBaseline = 0
/** 轮询句柄；不用 `ref`，它只影响行为不影响界面。 */
let poller: ReturnType<typeof setInterval> | null = null

/**
 * 正在跑的这一轮流式请求的取消开关。
 *
 * 用途：用户切走会话 / 关掉页面时，把还在读的那条连接掐掉，
 * 否则它的字会继续往**已经切走的那个会话**上贴。
 * 后端也会因为连接断开而停止本轮，不会留下一条写到一半的记录。
 */
let inFlight: AbortController | null = null

// ------------------------- 会话列表 -------------------------

// limit 给 50：会话是越用越多的东西，首页只做入口，不做分页浏览。
const {
  state: listState,
  data: listPage,
  error: listError,
  reload: reloadList,
} = useApi(() => fetchConversations({ limit: 50 }))

const conversations = computed(() => listPage.value?.items ?? [])

// ------------------------- 当前会话的消息 -------------------------

// `useApi` 里的 `watchEffect` 会自动把 `selectedId.value` 记成依赖，
// 所以选中项一变，这个请求自己就重发了 —— 不用再手写一层"监听选中项"。
const {
  state: messageState,
  data: messagePage,
  error: messageError,
  reload: reloadMessages,
} = useApi(() =>
  selectedId.value === null
    ? Promise.resolve(null)
    : fetchConversationMessages(selectedId.value, { limit: 100 }),
)

// 历史只在这里铺一次底；之后本轮的增量直接追加进 `messages`。
watch(messagePage, (page) => {
  messages.value = page === null ? [] : [...page.items]
})

// 切换会话先把上一轮的遗留清干净：否则新会话还没加载出来的那段时间，
// 屏幕上挂的还是上一个会话的对话或半截流式文字。
watch(selectedId, () => {
  cancelStream()
  messages.value = []
  optimistic.value = ''
  streamingText.value = ''
  turnStatus.value = null
  turnSources.value = []
  sendError.value = ''
  // 等待审批属于"某一条会话"，换了会话就不再成立了。
  stopWaiting()
})

/** 掐掉正在读的那条流；没有在跑就什么也不做。 */
function cancelStream(): void {
  if (inFlight !== null) {
    inFlight.abort()
    inFlight = null
    sending.value = false
  }
}

// 离开这个页面时把定时器和流都收干净，否则定时器会在后台一直打接口、
// 流会在后台一直往内存里追加（人已经看不见了）。
onUnmounted(() => {
  stopWaiting()
  cancelStream()
})

// ------------------------- 发送 -------------------------

const canSend = computed(
  () =>
    selectedId.value !== null
    && draft.value.trim() !== ''
    && !sending.value
    // 暂停中的会话发出去也只会拿到 409，干脆别让点。
    && !waiting.value,
)

/**
 * 追加服务端返回的消息，按 id 去重。
 *
 * 去重的意义：`:key` 用的是消息 id，真出现重复 id 时 Vue 会报警并且渲染错乱。
 * 正常一轮不会重复，但"没收到响应又点了一次"这类情况可能让同一条回来两遍。
 */
function appendMessages(incoming: ChatMessage[]): void {
  const seen = new Set(messages.value.map((message) => message.id))
  for (const message of incoming) {
    if (seen.has(message.id)) continue
    seen.add(message.id)
    messages.value.push(message)
  }
}

/**
 * 进入"等待审批"：锁输入框 + 每几秒重读一次历史。
 *
 * 为什么轮询而不是等推送：这个接口是非流式的，审批发生在**另一个人的浏览器**上
 * （管理员），服务端没有任何通道能通知到这里。间隔取 4 秒是折中 —— 真等到了也就慢几秒，
 * 用户一直不处理也不会把接口打爆。
 */
function startWaiting(requestKey: string | null): void {
  waiting.value = true
  waitingRequestKey.value = requestKey
  waitingBaseline = messages.value.length
  if (poller !== null) return
  poller = setInterval(() => {
    // 正在发消息时别插队，那一轮自己会带回结果。
    if (!sending.value) reloadMessages()
  }, 4000)
}

/** 离开"等待审批"：解锁输入框并停掉轮询。 */
function stopWaiting(): void {
  waiting.value = false
  waitingRequestKey.value = null
  if (poller !== null) {
    clearInterval(poller)
    poller = null
  }
}

/** 把一条错误翻成界面上那句话，并顺手处理 409。 */
function failSend(err: unknown, content: string): void {
  // 不自动重发：上一轮可能已经把退款申请写进库了，自动重试会多出一条申请。
  // 把输入还回去，让用户看过错误之后再决定。
  draft.value = content
  if (err instanceof ApiError && err.status === 409 && err.message.includes('审批')) {
    // 刷新页面后界面上没有"正在等待"这个状态（历史接口不返回它），
    // 但后端一挡就是 409 —— 拿这个当信号把状态补回来，不然用户会一直点、一直失败。
    sendError.value = ''
    startWaiting(null)
    return
  }
  sendError.value = err instanceof ApiError ? err.message : '消息发送失败'
}

/** 一轮跑完了，把服务端的结果铺到界面上（流式、非流式走的是同一套）。 */
function applyTurn(target: string, turn: MessageTurn): void {
  // 结果属于发起时那个会话；拿回来再核一次，别贴到别的会话上。
  if (selectedId.value !== target) return
  // ⚠️ 服务端返回的 `messages` **包含刚发的那条用户消息**（`done` 已定稿）：
  // 整段追加即可，不要再把 `content` 单独插一遍，否则你那句话会显示两遍。
  appendMessages(turn.messages)
  // 这一轮是不是把图停在"等管理员审批"了，由后端说了算（`status` 字段）。
  if (turn.status === 'waiting_approval') {
    startWaiting(turn.pending_request_key)
  } else {
    stopWaiting()
  }
}

// 轮询把历史读回来之后，只要消息变多了，就说明管理员已经决策、服务端把结果追加进来了。
watch(
  () => messages.value.length,
  (count) => {
    if (waiting.value && count > waitingBaseline) stopWaiting()
  },
)

async function send(): Promise<void> {
  const content = draft.value.trim()
  const target = selectedId.value
  if (content === '' || target === null || sending.value) return

  sending.value = true
  sendError.value = ''
  turnStatus.value = null
  turnSources.value = []
  streamingText.value = ''
  optimistic.value = content
  draft.value = ''

  try {
    await runStream(target, content)
  } catch (err) {
    // AbortError 是我们自己掐的（切会话 / 关页面），不算失败，别弹错误。
    if (!(err instanceof DOMException && err.name === 'AbortError')) {
      failSend(err, content)
    }
  } finally {
    optimistic.value = ''
    streamingText.value = ''
    inFlight = null
    sending.value = false
    // 后端已经更新了会话的最近活动时间，列表顺序要跟着动。
    reloadList()
  }
}

/**
 * 走流式接口，边收边显示。
 *
 * 三个阶段，界面表现完全不同：
 * 1. **发出去了、还没回音** —— `optimistic` 显示你刚说的那句，旁边占位"正在回复…"。
 *    ⚠️ 这段可能不短：模型要先看订单、可能还要检索，才有第一个字。
 * 2. **开始吐字** —— `streamingText` 逐个追加。此时**什么数据都还没落库**，
 *    所以它只是个草稿，不能塞进 `messages`。
 * 3. **`done` 事件到** —— 把草稿丢掉、换成服务端返回的正式消息（含你自己那条）。
 *
 * 另有一个坑：流式响应的 **HTTP 状态码早就 200 发出去了**，中途出错后端只能直接
 * 断流。所以"循环结束了却没等到 `done`"就是失败 —— 必须当错误报出来，
 * 否则用户看到一段残缺的话，还以为这就是答案。
 */
async function runStream(target: string, content: string): Promise<void> {
  inFlight = new AbortController()
  const signal = inFlight.signal

  let turn: MessageTurn | null = null
  for await (const event of streamConversationMessage(target, content, signal)) {
    if (event.type === 'delta') {
      streamingText.value += event.text
    } else if (event.type === 'done') {
      turn = event.turn
    }
  }

  if (turn === null) {
    throw new ApiError(0, '本轮回复中断，请查看历史消息确认结果后再重新发送')
  }

  // 先把正式消息铺上，再清草稿 —— 顺序反过来的话会闪一下空窗。
  applyTurn(target, turn)
  streamingText.value = ''
  turnStatus.value = turn.retrieval_status
  turnSources.value = turn.retrieved_sources
}

// ------------------------- 新建与切换 -------------------------

async function startConversation(): Promise<void> {
  if (creating.value || sending.value) return
  creating.value = true
  sendError.value = ''
  try {
    const created = await createConversation()
    // 新会话还没有消息，直接选中它就能接着提问，不用去列表里找。
    selectedId.value = created.id
    reloadList()
  } catch (err) {
    sendError.value = err instanceof ApiError ? err.message : '新建会话失败'
  } finally {
    creating.value = false
  }
}

function selectConversation(id: string): void {
  selectedId.value = id
}
</script>

<template>
  <div class="stack">
    <header class="page-head">
      <h2 class="page-head__title">你好，{{ user?.username }}</h2>
      <p class="page-head__desc">可以查询订单、咨询售后政策、提交退款申请。</p>
    </header>

    <div class="card-grid">
      <RouterLink class="entry-card" to="/customer/orders">
        <span class="entry-card__title">我的订单</span>
        <span class="entry-card__desc">查看订单详情与退款资格</span>
      </RouterLink>
      <RouterLink class="entry-card" to="/customer/refund-requests">
        <span class="entry-card__title">我的退款申请</span>
        <span class="entry-card__desc">查看申请进度与审批意见</span>
      </RouterLink>
    </div>

    <div class="chat-layout">
      <aside class="chat-layout__side">
        <div class="side-head side-head--row">
          <span>会话</span>
          <!-- 一轮没跑完之前不让切走：结果要贴回发起时那个会话，切了就对不上。
               后端那边同一个会话也会返回 409，这里只是提前避免。 -->
          <button
            type="button"
            class="btn btn--ghost btn--sm"
            :disabled="creating || sending"
            @click="startConversation"
          >
            {{ creating ? '创建中…' : '+ 新建' }}
          </button>
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
          :disabled="sending"
          @select="selectConversation"
        />
      </aside>

      <section class="chat-layout__main">
        <div v-if="selectedId === null" class="chat-empty">
          <p class="chat-empty__title">选一个会话开始</p>
          <p class="muted">左边点一个已有的会话，或者点「+ 新建」开一个新的。</p>
        </div>

        <template v-else>
          <div v-if="messageState === 'loading'" class="pane-pad">
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
          />

          <RetrievedSources v-if="turnStatus" :status="turnStatus" :sources="turnSources" />

          <div v-if="sendError" class="pane-pad">
            <ErrorAlert :message="sendError" />
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

          <form class="composer" @submit.prevent="send">
            <input
              v-model="draft"
              class="composer__input"
              :disabled="sending || waiting"
              maxlength="8000"
              :placeholder="waiting
                ? '正在等待管理员审批，这一轮结束前不能发新消息'
                : '问点什么，比如「索尼 WH-1000XM5 怎么用有线模式」'"
            />
            <button type="submit" class="btn btn--primary" :disabled="!canSend">
              {{ sending ? '回复中…' : '发送' }}
            </button>
          </form>
        </template>
      </section>
    </div>

    <PlaceholderBlock title="还没做的部分">
      <ul class="plain-list">
        <li>断线恢复：发送过程中刷新页面，这一轮就看不到了，重进会话才会从历史里读回来。</li>
        <li>等待审批的状态：刷新页面后界面认不出来（历史接口还没返回这个字段），要等下次发送被 409 挡回来才知道。</li>
      </ul>
    </PlaceholderBlock>
  </div>
</template>
