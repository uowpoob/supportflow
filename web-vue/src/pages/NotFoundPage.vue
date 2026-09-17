<script setup lang="ts">
import { RouterLink } from 'vue-router'
</script>

<template>
  <div class="center-page">
    <div class="card center-card">
      <h2 class="center-card__title">404 页面不存在</h2>
      <p class="muted">地址写错了，或者这个页面还没做。</p>
      <RouterLink class="btn btn--primary" to="/">回到首页</RouterLink>
    </div>
  </div>
</template>
