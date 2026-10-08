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
import AppIcon from '../../components/common/AppIcon.vue'
import ErrorAlert from '../../components/common/ErrorAlert.vue'
import LoadingLine from '../../components/common/LoadingLine.vue'
import { useApi } from '../../composables/useApi'
import type {
  ChatMessage,
  ConversationMessages,
  MessageTurn,
  RetrievalStatus,
  RetrievedSource,
} from '../../types'

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

/**
 * 正在建会话。
 *
 * 只有一种情况会为真：还没选中任何会话时发出第一句话，`send` 先去建一个空会话
 * （见 `send` 里那段）。这期间发送按钮显示「创建中…」。
 */
const creating = ref(false)

/**
 * 会话被"暂停"在图里等管理员审批 —— 这是后端 `wait_for_approval` 节点的中断态。
 *
 * 三条约定（都跟后端契约绑定，别自己加戏）：
 * - 暂停期间**发消息一定被后端 409 挡回来**，所以输入框必须锁上，别让用户白点。
 * - 审批完成后由**服务端**往这条会话追加一条回复，前端只是把它读回来：
 *   接口没有推送，只能隔几秒问一次历史接口。
 * - **刷新页面也认得出来**：历史接口现在会返回 `status` / `pending_request_key`
 *   （见 `types.ts::ConversationMessages`），进来读一次就有了，不用再靠 409 反推。
 */
const waiting = ref(false)
/** 暂停中的那张申请编号；只有服务端明确告诉我们时才有值。 */
const waitingRequestKey = ref<string | null>(null)
/** 开始等待那一刻已有多少条消息 —— 审批结果一到，条数就比它多。 */
let waitingBaseline = 0
/** 轮询句柄；不用 `ref`，它只影响行为不影响界面。 */
let poller: ReturnType<typeof setInterval> | null = null

/**
 * 已确认处于等待审批的会话 id 集合。
 *
 * 只放**服务端确认过**的（发消息时返回的 `status`，或进会话读历史得到的）。
 * 会话列表接口不返回这个状态，所以没进过的会话这里没有 —— 列表上就标不出来，
 * 这是当前接口的边界，不靠猜来补。
 */
const waitingIds = ref<string[]>([])

/**
 * 后端说这个会话正有一轮在跑，但**不是这一页发起的**。
 *
 * 怎么进来的（只有一条路）：
 * - 界面上以为这个会话空闲，发出去被后端 409 挡回来 → 说明上一条流断了、服务端还在跑
 *   （典型来源是发送过程中刷新了页面）。
 *
 * ⚠️ **历史接口读不出"正在跑"**（`ConversationMessagesOut` 没有这个字段，
 * 见 `types.ts` 里 `ConversationRunningStatus` 那段）。所以刷新之后进会话时是认不出来的：
 * 页面上输入框是能用的，要等用户点一次发送、被 409 顶回来才补上这个状态。
 * 这是当前接口下的降级行为，不靠猜来补。
 *
 * 认出之后：界面显示"正在回复"占位 + 锁住输入框，并隔几秒重读历史 ——
 * 那一轮跑完的结果会由服务端追加，靠轮询发现（`runningElsewhere` 转 false）。
 */
const runningElsewhere = ref(false)
/** 判断"变多了"的基线：进入这个状态时历史里已有多少条。 */
let runningBaseline = 0
/** 只用来画提示卡片：当前会话是不是"正在跑但不是我发的"。 */
const showRunning = computed(
  () => runningElsewhere.value && !waiting.value && !sending.value,
)

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
  // 每次读到新的一页，"等审批"的基线就跟着当前条数走。
  // （审批结果是审批那一刻之后才追加的，拿新的一页当基线不会漏掉它。）
  if (waiting.value) waitingBaseline = messages.value.length
  // 后端是这个会话状态的唯一权威：进会话、以及每次轮询回来，都用它校正界面。
  // 刷新之后"等审批"就是靠这一句认回来的。
  applyServerStatus(page)
})

/**
 * 拿服务端返回的状态校正界面上的 `waiting`。
 *
 * 这是"刷新之后界面认不认得出这个会话在等审批"的**唯一依据** ——
 * 进会话时读一次、之后每次轮询回来再校正一次。
 *
 * 只在"这一页自己没在发送"时校正：本页正在发消息时它自己会带回结果，
 * 轮询也已经停掉，此时去改状态只会跟它打架。
 *
 * ⚠️ 这里**处理不了"正在跑"**。历史接口不返回那个状态，无从判断；
 * 那种情况由 `failSend` 在收到 409 时补记。等后端补字段了，在这里加一个分支即可
 * （`types.ts::ConversationRunningStatus` 记着该怎么改）。
 */
function applyServerStatus(page: ConversationMessages | null): void {
  if (sending.value || page === null) return
  // 服务端说这个会话正有一轮在跑（比如本页发起的流在刷新时断了、服务端还在跑）。
  // 之前接口不返回这个状态、只能等发送被 409 挡回来才补记；现在历史接口直接给了。
  if (page.running) {
    startRunningElsewhere()
    return
  }
  if (page.status !== 'waiting_approval') {
    // 服务端说这个会话没在等审批。可能是刚被别人批准了，也可能本来就是正常的。
    if (waiting.value) stopWaiting()
    return
  }
  // 已经在等同一张申请就别重启：重启没有意义，还会打乱轮询节奏。
  if (waiting.value && waitingRequestKey.value === page.pending_request_key) {
    rememberWaiting(page.conversation_id, true)
    return
  }
  startWaiting(page.pending_request_key)
}

/**
 * 切到另一条会话之前，先把上一条留在屏幕上的东西清干净。
 *
 * 不清的话，新会话还没加载出来的那段时间，屏幕上挂的还是上一个会话的对话
 * 或者半截流式文字。
 *
 * ⚠️ **只有"用户点了左边列表"才调它**（见 `selectConversation`），
 * 千万别挂回 `watch(selectedId)`：没选会话时发第一句话会先建一个新会话、
 * 把 `selectedId` 从 null 改成它的 id，那一刻根本没有"上一轮的遗留"要清，
 * 而清理第一步的 `cancelStream()` 会把**刚发出去的那一轮**掐死。
 *
 * 顺序也有讲究：**先清再改 `selectedId`** —— `stopWaiting` 要拿旧的 id
 * 才能把列表上那个「等审批」角标销掉。
 */
function clearTurnState(): void {
  cancelStream()
  messages.value = []
  optimistic.value = ''
  streamingText.value = ''
  turnStatus.value = null
  turnSources.value = []
  sendError.value = ''
  // "等审批"和"正在跑"都属于**某一条会话**，换了会话就不再成立：
  // 新会话的历史一回来就会按它自己的状态重新判一遍（见 `applyServerStatus`），
  // 所以这里可以放心清掉，不会丢信息。
  stopWaiting()
  stopRunningElsewhere()
}

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
  stopRunningElsewhere()
  cancelStream()
})

// ------------------------- 发送 -------------------------

/**
 * 能不能点发送。
 *
 * ⚠️ **不需要先选中会话**：没选就是"还没有会话"，发送时会先自动建一个再发
 * （见 `send`）。所以这里只看这句话能不能发，不看会话有没有。
 */
const canSend = computed(
  () =>
    draft.value.trim() !== ''
    && !sending.value
    // 这两种状态下发出去都只会拿到 409，干脆别让点。
    && !waiting.value
    && !runningElsewhere.value,
)

/**
 * 消息区要不要显示"加载中"。
 *
 * 正在发消息时**不算**加载：自动建会话那一下会顺带触发一次历史请求（空会话），
 * 不挡住的话，屏幕上刚出现的对话和刚发出去的那句话会被骨架屏顶掉闪一下。
 */
const loadingMessages = computed(() => messageState.value === 'loading' && !sending.value)

/** 输入框里那句提示 —— 锁上时要说明"为什么现在不能发"。 */
const inputPlaceholder = computed(() => {
  if (waiting.value) return '正在等待管理员审批，这一轮结束前不能发新消息'
  if (runningElsewhere.value) return '上一条还在回复中，等它结束再发下一条'
  return '问点什么，比如「索尼 WH-1000XM5 怎么用有线模式」'
})

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
 * 只要"后台还有活没落地"，就每隔几秒重读一次历史。
 *
 * 两种情形合用一个定时器（不各开一个，否则同一条会话会同时打两份接口）：
 * - **等待管理员审批**：决策发生在另一个人的浏览器上，服务端没有通道能通知这里；
 * - **本页发起的流断掉了、但服务端还在跑**（刷新过页面）：结果什么时候落库也不知道。
 *
 * 4 秒是折中：真等到了也就慢几秒，用户一直不处理也不会把接口打爆。
 */
function syncPolling(): void {
  if (waiting.value || runningElsewhere.value) {
    if (poller !== null) return
    poller = setInterval(() => {
      // 正在发消息时别插队，那一轮自己会带回结果。
      if (!sending.value) reloadMessages()
    }, 4000)
    return
  }
  if (poller !== null) {
    clearInterval(poller)
    poller = null
  }
}

/** 进入"等待审批"：锁输入框 + 开始轮询。 */
function startWaiting(requestKey: string | null): void {
  waiting.value = true
  waitingRequestKey.value = requestKey
  waitingBaseline = messages.value.length
  // 已经在等审批就不再是"在跑"，两件事叠在一起会让提示自相矛盾。
  runningElsewhere.value = false
  if (selectedId.value !== null) rememberWaiting(selectedId.value, true)
  syncPolling()
}

/** 离开"等待审批"：解锁输入框，可能还有别的活，交给 `syncPolling` 决定停不停。 */
function stopWaiting(): void {
  waiting.value = false
  waitingRequestKey.value = null
  if (selectedId.value !== null) rememberWaiting(selectedId.value, false)
  syncPolling()
}

/** 把"这个会话在等审批"记进/移出那个集合（列表上的角标靠它）。 */
function rememberWaiting(id: string, active: boolean): void {
  const rest = waitingIds.value.filter((item) => item !== id)
  waitingIds.value = active ? [...rest, id] : rest
}

/**
 * 进入"后台还在跑"：锁输入框 + 开始轮询，等消息变多。
 *
 * 只有一个调用点：发送被 409 挡回来的时候（`failSend`）。进来的前提是这一页
 * 之前没发现过它 —— 进会话读历史时认不出来（接口不返回这个状态）。
 */
function startRunningElsewhere(): void {
  runningElsewhere.value = true
  runningBaseline = messages.value.length
  syncPolling()
}

function stopRunningElsewhere(): void {
  // 没在跑就别动基线：`stopXxx` 在切会话时也会被无条件调一次，
  // 顺手把基线清了会让"刚记下的基线"显得像没生效过，读代码时容易误解。
  if (!runningElsewhere.value) return
  runningElsewhere.value = false
  runningBaseline = 0
  syncPolling()
}

/** 把一条错误翻成界面上那句话，并顺手处理 409。 */
function failSend(err: unknown, content: string): void {
  // 不自动重发：上一轮可能已经把退款申请写进库了，自动重试会多出一条申请。
  // 把输入还回去，让用户看过错误之后再决定。
  draft.value = content
  if (err instanceof ApiError && err.status === 409) {
    // 后端 409 只有两个原因（见 `docs/conversation-api.md` 的状态码表），
    // 靠文案分派到对应的那个界面状态。文案以后要改的话，这里得跟着改。
    //
    // 兜底：正常刷新过页面的话，进会话读历史就已经认出这两种状态了 ——
    // 会走到这里，说明是"这一页的界面状态过时了"（比如后台标签页刚切回来），
    // 所以只管纠正、不用弹错误。
    sendError.value = ''
    if (err.message.includes('审批')) startWaiting(null)
    else startRunningElsewhere()
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
  // 首轮后后端生成了标题：立刻反映到左侧列表，别等下一次 reload 才出现。
  if (turn.title && listPage.value !== null) {
    const newTitle = turn.title
    const page = listPage.value
    listPage.value = {
      ...page,
      items: page.items.map((item) =>
        item.id === target ? { ...item, title: newTitle } : item,
      ),
    }
  }
  // 这一轮是不是把图停在"等管理员审批"了，由后端说了算（`status` 字段）。
  if (turn.status === 'waiting_approval') {
    startWaiting(turn.pending_request_key)
  } else {
    stopWaiting()
    stopRunningElsewhere()
  }
}

// 轮询把历史读回来之后，只要消息变多了，就说明活干完了。
// 两个状态各有一条：等审批时"变多"= 管理员决策完、服务端把结果追加进来了；
// 断线那一轮"变多"= 服务端终于把这一轮跑完并落库了。
watch(
  () => messages.value.length,
  (count) => {
    if (waiting.value && count > waitingBaseline) stopWaiting()
    if (runningElsewhere.value && count > runningBaseline) stopRunningElsewhere()
  },
)
async function send(): Promise<void> {
  const content = draft.value.trim()
  if (content === '' || sending.value || creating.value || waiting.value || runningElsewhere.value) {
    return
  }

  sending.value = true
  sendError.value = ''
  turnStatus.value = null
  turnSources.value = []
  streamingText.value = ''
  optimistic.value = content
  draft.value = ''

  try {
    // 还没选中任何会话 = 这是进来之后的第一句话：先建一个空会话，再把这句发进去。
    // 界面上没有「+ 新建」按钮，会话就是在这一步悄悄出现的。
    let target = selectedId.value
    if (target === null) {
      creating.value = true
      const created = await createConversation()
      target = created.id
      // 选中新会话：右边会去读它的历史（空的一页，`loadingMessages` 已经挡住了
      // 那一下的骨架屏），左边列表刷新后它立刻排在最前面。
      selectedId.value = created.id
      reloadList()
      creating.value = false // 建好了，后面就是普通发送，按钮切回「回复中…」
    }
    await runStream(target, content)
  } catch (err) {
    // AbortError 是我们自己掐的（切会话 / 关页面），不算失败，别弹错误。
    // ⚠️ 注意：**用户刷新页面**也会走到这里（浏览器把连接断掉），
    // 但那种情况下这个组件已经销毁了，什么都不用做 ——
    // 那一轮的下场由"重新进这个会话读历史"接手（见 `applyServerStatus`）。
    if (!(err instanceof DOMException && err.name === 'AbortError')) {
      failSend(err, content)
    }
  } finally {
    // 兜底：建会话那一步要是抛了，别让按钮永远卡在「创建中…」。
    creating.value = false
    optimistic.value = ''
    streamingText.value = ''
    inFlight = null
    sending.value = false
    // 轮询在发送期间是停的，这里结束后要重新看一眼后台还有没有活。
    syncPolling()
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

// ------------------------- 切换会话 -------------------------
// 新建不在这里 —— 会话是发第一句话时自动建的，见 `send`。

/**
 * 点左边列表切过去。
 *
 * 点已经选中的那一条什么都不做：重来一遍会把屏幕上的对话清掉、再读一次历史，
 * 白闪一下，什么也没多出来。
 */
function selectConversation(id: string): void {
  if (id === selectedId.value) return
  clearTurnState()
  selectedId.value = id
}

// ------------------------- 删除会话 -------------------------

/** 正在删除的会话 id；删除期间列表上那条要有个"忙"的样子，也挡住重复点。 */
const deletingId = ref<string | null>(null)

/**
 * 删除一条会话（列表上的垃圾桶图标触发）。
 *
 * 只删自己确认过的那一条；删的是当前选中的会话时，先把屏幕上的对话清掉、
 * 选中态回到"没选"，再刷新列表 —— 否则右边还挂着已删除会话的对话。
 */
async function removeConversation(id: string): Promise<void> {
  if (deletingId.value !== null) return
  if (!window.confirm('确定删除这个会话吗？对话记录和它关联的退款申请会一起删除，且无法恢复。')) {
    return
  }
  deletingId.value = id
  try {
    await deleteConversation(id)
    // 删的是正在看的这条：回到"没选中"的空状态，别让已删除的对话继续挂在屏幕上。
    if (selectedId.value === id) {
      clearTurnState()
      selectedId.value = null
    }
    // 等审批的角标集合里也清掉它，别留一个指向已删会话的角标。
    rememberWaiting(id, false)
    await reloadList()
  } catch (err) {
    sendError.value = err instanceof ApiError ? err.message : '删除失败，请重试'
  } finally {
    deletingId.value = null
  }
}
</script>

<template>
  <div class="stack">
    <header class="page-head">
      <h2 class="page-head__title">你好，{{ user?.username }}</h2>
      <p class="page-head__desc">可以查询订单、咨询售后政策、提交退款申请。</p>
    </header>

    <div class="card-grid">
      <RouterLink class="entry-card entry-card--blue" to="/customer/orders">
        <span class="entry-card__icon"><AppIcon name="box" :size="20" /></span>
        <span class="entry-card__title">我的订单</span>
        <span class="entry-card__desc">查看订单详情与退款资格</span>
      </RouterLink>
      <RouterLink class="entry-card entry-card--amber" to="/customer/refund-requests">
        <span class="entry-card__icon"><AppIcon name="receipt" :size="20" /></span>
        <span class="entry-card__title">我的退款申请</span>
        <span class="entry-card__desc">查看申请进度与审批意见</span>
      </RouterLink>
    </div>

    <div class="chat-layout">
      <aside class="chat-layout__side">
        <!-- 这里原来有个「+ 新建」按钮，已经去掉了：会话改成"发第一句话时自动建"
             （见 `send`），用户不用先操心会话从哪来，也就没有"一直点新建"这回事。 -->
        <div class="side-head">
          <span class="side-head__label"><AppIcon name="chat" :size="16" />会话</span>
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
        <!-- 还没选中会话也直接给一个空聊天区（像 ChatGPT 那样：进来就能打字，
             不用先点左边列表）。发送时 `send` 会先建一个会话、再把这句发进去。 -->
        <ChatThread
          v-if="selectedId === null"
          :messages="messages"
          :pending="sending"
          :optimistic="optimistic"
          :streaming="streamingText"
          :running-elsewhere="showRunning"
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

        <!-- 后台还在跑，但不是这个页面发起的（典型：发送过程中刷新了页面）。
             服务端那一轮没有因为断线停下来，结果出来之前也发不了新消息。 -->
        <div v-else-if="showRunning" class="pane-pad">
          <div class="alert alert--info alert--row">
            <span>
              上一条消息还在回复中（页面刷新过，这里接不上原来的连接）。
              完成后会自动出现在上面的对话里。
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
            :disabled="sending || waiting || runningElsewhere"
            :placeholder="inputPlaceholder"
          />
          <button type="submit" class="btn btn--primary btn--icon" :disabled="!canSend">
            <AppIcon name="send" :size="15" />
            <span>{{ sending ? (creating ? '创建中…' : '回复中…') : '发送' }}</span>
          </button>
        </form>
      </section>
    </div>
  </div>
</template>
