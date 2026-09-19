<script setup lang="ts">
import { RouterView } from 'vue-router'

import { useAuth } from './auth/useAuth'
import AuthLoading from './components/common/AuthLoading.vue'

// 对应 React 版的 `RootRedirect` + `<Routes>`：
// 分流逻辑搬进了 router.ts 的全局守卫，这里只剩"身份没确认完就先别渲染页面"。
const { initializing } = useAuth()
</script>

<template>
  <!-- 身份确认之前不渲染路由视图 —— 否则会先按"未登录"渲染出登录表单，
       等 `/me` 回来再跳走，用户看到的是闪一下。 -->
  <AuthLoading v-if="initializing" />
  <RouterView v-else />
</template>
