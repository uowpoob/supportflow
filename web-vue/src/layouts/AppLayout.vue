<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'

import { ApiError } from '../api/client'
import { roleLabel } from '../auth/paths'
import { useAuth } from '../auth/useAuth'
import AppIcon from '../components/common/AppIcon.vue'
import type { NavItem } from './nav'

defineProps<{ nav: NavItem[] }>()

const { user, signOut, signingOut } = useAuth()
const router = useRouter()
const route = useRoute()
const signOutError = ref<string | null>(null)

/**
 * 当前是否停在这一项上。
 *
 * React 版的 `NavLink` 会给一个 `isActive` 回调，这里自己算：
 * 带 `end` 的项必须精确匹配 —— 否则 `/customer` 是所有子页面的前缀，
 * 走进「我的订单」时两个菜单项会一起亮。
 */
function isActive(item: NavItem): boolean {
  if (item.end) return route.path === item.to
  return route.path === item.to || route.path.startsWith(`${item.to}/`)
}

async function handleSignOut() {
  signOutError.value = null
  try {
    await signOut()
    // 只有服务端真的撤销成功才离开 —— 本地状态跟着服务端走。
    await router.replace({ name: 'login' })
  } catch (err) {
    // 服务端那条会话很可能还在，此时**绝不能**跳转或清空界面：
    // 否则用户以为退出了，刷新一下却又是登录态。
    // 正确做法是留在当前页、说明原因、让他重试。
    signOutError.value = err instanceof ApiError ? err.message : '退出登录失败，请重试'
  }
}
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <!-- .topbar__inner 走和正文一样的总宽度：商标、用户名跟下面的卡片左右对齐。 -->
      <div class="topbar__inner">
        <div class="topbar__brand">
          <span class="topbar__logo" aria-hidden="true">SF</span>
          <span class="topbar__title">SupportFlow</span>
        </div>

        <nav class="topbar__nav" aria-label="主导航">
          <RouterLink
            v-for="item in nav"
            :key="item.to"
            :to="item.to"
            :class="isActive(item) ? 'navlink navlink--active' : 'navlink'"
          >
            <AppIcon v-if="item.icon" :name="item.icon" :size="16" />
            <span>{{ item.label }}</span>
          </RouterLink>
        </nav>

        <div class="topbar__user">
          <template v-if="user">
            <span class="userchip">
              <span class="userchip__name">{{ user.username }}</span>
              <span class="userchip__role" :class="`userchip__role--${user.role}`">
                {{ roleLabel(user.role) }}
              </span>
            </span>
            <button type="button" class="btn btn--ghost" :disabled="signingOut" @click="handleSignOut">
              {{ signingOut ? '退出中…' : '退出' }}
            </button>
          </template>
        </div>
      </div>
    </header>

    <main class="page">
      <div v-if="signOutError" class="alert alert--error alert--row" role="alert">
        <div>
          <div class="alert__title">退出登录失败，服务端会话可能仍然有效</div>
          <div>{{ signOutError }}</div>
        </div>
        <button type="button" class="btn btn--ghost" :disabled="signingOut" @click="handleSignOut">
          {{ signingOut ? '重试中…' : '重试' }}
        </button>
      </div>
      <RouterView />
    </main>
  </div>
</template>
