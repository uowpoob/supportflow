<script setup lang="ts">
import { RouterLink } from 'vue-router'

import { homePathFor } from '../auth/paths'
import { useAuth } from '../auth/useAuth'

const { user } = useAuth()
</script>

<template>
  <div class="center-page">
    <div class="card center-card">
      <h2 class="center-card__title">403 没有权限</h2>
      <p class="muted">当前账号（{{ user?.username }}）不能访问这个页面。</p>
      <RouterLink class="btn btn--primary" :to="user ? homePathFor(user.role) : '/login'">
        回到我的首页
      </RouterLink>
    </div>
  </div>
</template>
