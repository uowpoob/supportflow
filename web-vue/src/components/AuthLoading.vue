<script setup lang="ts">
/**
 * 首次向服务端确认身份时的占位页。
 *
 * 关键在于这一屏**不做任何判断** —— 既不跳登录页，也不渲染受保护的内容。
 * 因为 `/me` 返回之前 `user` 必然是 null，此刻若按"未登录"处理，
 * 每次打开页面都会先闪一下登录页再跳回来。
 */
</script>

<template>
  <div class="center-page">
    <div class="card center-card">
      <h2 class="center-card__title">正在恢复登录状态…</h2>
      <p class="muted">正在向服务端确认身份</p>
    </div>
  </div>
</template>
