<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '../../api/client'
import { returnPathFor } from '../../auth/paths'
import { useAuth } from '../../auth/useAuth'
import AppIcon from '../../components/common/AppIcon.vue'

const { user, signIn } = useAuth()
const route = useRoute()
const router = useRouter()

const username = ref('')
const password = ref('')
const showPassword = ref(false)
const error = ref<string | null>(null)
const details = ref<string[]>([])
const submitting = ref(false)
const usernameInput = ref<HTMLInputElement | null>(null)

/**
 * 已登录就别再让人看到登录表单。
 *
 * React 版是 `if (user) return <Navigate ... />` —— 每次渲染时判断一次。
 * Vue 里没有"重新渲染时判断"这回事，改成"盯着 `user` 这个 ref"：
 * 它一变成非空（刚登录成功，或带着有效 Cookie 走进来）就跳走。
 *
 * `immediate: true` 是为了覆盖"直接访问 /login"的情况；
 * 此时 `App.vue` 已经等过 `/me`，`user` 是确定值，不会误判。
 */
watch(
  user,
  (current) => {
    if (current) void router.replace(returnPathFor(current.role, route.query.from))
  },
  { immediate: true },
)

// React 的 `autoFocus` 属性在客户端渲染时不一定会真的聚焦（浏览器只在解析 HTML 时认它），
// 这里显式在挂载后调一次 focus()，效果更可靠。
onMounted(() => usernameInput.value?.focus())

async function handleSubmit() {
  error.value = null
  details.value = []
  submitting.value = true

  try {
    // 登录成功后由上面的 watch 统一跳转，避免两个跳转互相覆盖。
    await signIn({ username: username.value, password: password.value })
  } catch (err) {
    if (err instanceof ApiError) {
      error.value = err.message
      details.value = err.details
    } else {
      error.value = '登录失败，请稍后再试'
    }
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <section class="login-story" aria-label="SupportFlow 智能售后工作台">
      <div class="login-story__brand"><span class="topbar__logo"><AppIcon name="chat" :size="24" /></span>SupportFlow</div>
      <div class="login-story__content">
        <span class="eyebrow">SMART SUPPORT, SIMPLE FLOW</span>
        <h2>每一个售后问题，<br />都有更简单的解法。</h2>
        <p>从订单查询到退款处理，让智能助手连接每一步，<br class="desktop-break" />让你专注于真正重要的事。</p>
        <div class="login-preview" aria-hidden="true">
          <div class="login-preview__head"><AppIcon name="robot" :size="20" /><strong>你的售后助手</strong><span>咨询示例</span></div>
          <div class="login-preview__question">想了解我的订单是否可以申请退款</div>
          <div class="login-preview__answer">我会帮你核对订单状态与售后政策，<br />一步步完成退款申请。</div>
          <div class="login-preview__steps"><span><AppIcon name="box" :size="16" />订单查询</span><i>→</i><span><AppIcon name="search" :size="16" />政策核对</span><i>→</i><span><AppIcon name="receipt" :size="16" />退款申请</span></div>
        </div>
      </div>
      <div class="login-story__footer">更清晰的流程，更轻松的售后。</div>
    </section>
    <div class="login-form-wrap">
    <form class="card login-card" novalidate @submit.prevent="handleSubmit">
      <div class="login-card__head">
        <span class="eyebrow">欢迎来到 SUPPORTFLOW</span>
        <h1 class="login-card__title">欢迎回来</h1>
        <p class="login-card__subtitle">登录你的账号，继续处理售后事务。</p>
      </div>

      <div v-if="error" class="alert alert--error" role="alert">
        <div class="alert__title">{{ error }}</div>
        <ul v-if="details.length > 0" class="alert__list">
          <li v-for="item in details" :key="item">{{ item }}</li>
        </ul>
      </div>

      <label class="field">
        <span class="field__label">用户名</span>
        <input
          ref="usernameInput"
          v-model="username"
          class="field__input"
          name="username"
          placeholder="请输入用户名"
          autocomplete="username"
          required
        />
      </label>

      <div class="field">
        <label class="field__label" for="login-password">密码</label>
        <span class="password-field">
        <input
          v-model="password"
          id="login-password"
          class="field__input"
          name="password"
          :type="showPassword ? 'text' : 'password'"
          placeholder="请输入密码"
          autocomplete="current-password"
          required
        />
        <button type="button" class="password-toggle" :aria-label="showPassword ? '隐藏密码' : '显示密码'" :aria-pressed="showPassword" @click="showPassword = !showPassword">{{ showPassword ? '隐藏' : '显示' }}</button>
        </span>
      </div>

      <button type="submit" class="btn btn--primary btn--block" :disabled="submitting">
        {{ submitting ? '登录中…' : '登录' }} <span v-if="!submitting" aria-hidden="true">→</span>
      </button>
      <p class="login-card__foot"><AppIcon name="check-badge" :size="15" />登录后将进入对应角色的工作台</p>
    </form>
    <p class="login-copyright">SupportFlow · 智能售后工单助手</p>
    </div>
  </div>
</template>
