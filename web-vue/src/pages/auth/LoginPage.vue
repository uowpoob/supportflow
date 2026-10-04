<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '../../api/client'
import { returnPathFor } from '../../auth/paths'
import { useAuth } from '../../auth/useAuth'

const { user, signIn } = useAuth()
const route = useRoute()
const router = useRouter()

const username = ref('')
const password = ref('')
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
    <form class="card login-card" novalidate @submit.prevent="handleSubmit">
      <div class="login-card__head">
        <span class="topbar__logo" aria-hidden="true">SF</span>
        <h1 class="login-card__title">SupportFlow</h1>
        <p class="login-card__subtitle">智能售后工单助手</p>
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
          autocomplete="username"
          required
        />
      </label>

      <label class="field">
        <span class="field__label">密码</span>
        <input
          v-model="password"
          class="field__input"
          name="password"
          type="password"
          autocomplete="current-password"
          required
        />
      </label>

      <button type="submit" class="btn btn--primary btn--block" :disabled="submitting">
        {{ submitting ? '登录中…' : '登录' }}
      </button>
    </form>
  </div>
</template>
