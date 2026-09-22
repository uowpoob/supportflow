<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'

import {
  createConversation,
  fetchConversationMessages,
  fetchConversations,
  sendConversationMessage,
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
import type { ChatMessage, RetrievalStatus, RetrievedSource } from '../../types'

/**
 * 客户首页：快捷入口 + 左侧会话列表 + 右侧对话区。
 *
 * 数据分三块，各自独立：
 * - 会话列表：`GET /customer/conversations`
 * - 历史消息：`GET /customer/conversations/{id}/messages`（选中哪个拉哪个）
 * - 发消息：  `POST /customer/conversations/{id}/messages`（非流式，等整轮跑完）
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
const sendError = ref('')

/** 本轮的检索状态与依据 —— 属于"这一轮"，不混进消息列表。 */
const turnStatus = ref<RetrievalStatus | null>(null)
const turnSources = ref<RetrievedSource[]>([])

const creating = ref(false)

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

// 切换会话先清空：否则新会话还没加载出来的那段时间，屏幕上挂的还是上一个会话的对话。
watch(selectedId, () => {
  messages.value = []
  optimistic.value = ''
  turnStatus.value = null
  turnSources.value = []
  sendError.value = ''
})

// ------------------------- 发送 -------------------------

const canSend = computed(
  () => selectedId.value !== null && draft.value.trim() !== '' && !sending.value,
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

async function send(): Promise<void> {
  const content = draft.value.trim()
  const target = selectedId.value
  if (content === '' || target === null || sending.value) return

  sending.value = true
  sendError.value = ''
  turnStatus.value = null
  turnSources.value = []
  optimistic.value = content
  draft.value = ''

  try {
    const turn = await sendConversationMessage(target, content)
    // 结果属于发起时那个会话；拿回来再核一次，别贴到别的会话上。
    if (selectedId.value === target) {
      // ⚠️ 服务端返回的 `messages` **包含刚发的那条用户消息**（`done` 已定稿）：
      // 整段追加即可，不要再把 `content` 单独插一遍，否则你那句话会显示两遍。
      appendMessages(turn.messages)
      turnStatus.value = turn.retrieval_status
      turnSources.value = turn.retrieved_sources
    }
    // 后端已经更新了会话的最近活动时间，列表顺序要跟着动。
    reloadList()
  } catch (err) {
    // 不自动重发：上一轮可能已经把退款申请写进库了，自动重试会多出一条申请。
    // 把输入还回去，让用户看过错误之后再决定。
    draft.value = content
    sendError.value = err instanceof ApiError ? err.message : '消息发送失败'
  } finally {
    optimistic.value = ''
    sending.value = false
  }
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

          <ChatThread v-else :messages="messages" :pending="sending" :optimistic="optimistic" />

          <RetrievedSources v-if="turnStatus" :status="turnStatus" :sources="turnSources" />

          <div v-if="sendError" class="pane-pad">
            <ErrorAlert :message="sendError" />
          </div>

          <form class="composer" @submit.prevent="send">
            <input
              v-model="draft"
              class="composer__input"
              :disabled="sending"
              maxlength="8000"
              placeholder="问点什么，比如「索尼 WH-1000XM5 怎么用有线模式」"
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
        <li>流式输出：现在是<strong>非流式</strong>，要等整轮（模型 + 工具 + 检索）跑完才一次性出结果。</li>
        <li>断线恢复：发送过程中刷新页面，这一轮就看不到了，重进会话才会从历史里读回来。</li>
      </ul>
    </PlaceholderBlock>
  </div>
</template>
