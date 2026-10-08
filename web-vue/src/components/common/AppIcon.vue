<script setup lang="ts">
import { computed } from 'vue'

/**
 * 项目里所有的小图标都在这里，集中管理。
 *
 * 为什么自己写而**不装图标库**：这套界面一共只要十来个图标，
 * 为了它们多引一个依赖、多一份体积不划算；更重要的是图标要跟着
 * 主色走（`currentColor`），换主题时不用逐个替换。
 *
 * 画法：24×24 的网格，只描边不填充（`fill: none`），
 * 线条粗细由 CSS 的 `stroke-width` 控制 —— 同一个图标放大也不用改数据。
 */

/** 一个图标可以由这几种基本形状拼出来。 */
type Shape =
  | { t: 'path'; d: string }
  | { t: 'circle'; cx: number; cy: number; r: number }
  | { t: 'line'; x1: number; y1: number; x2: number; y2: number }
  | { t: 'rect'; x: number; y: number; w: number; h: number; r?: number }

/**
 * 图标字典。新增一枚图标 = 在这里加一条。
 *
 * 坐标是 24×24 里的绝对数值；想微调就改数字，别改 viewBox。
 */
const ICONS: Record<string, Shape[]> = {
  // 房子：概览 / 首页
  home: [
    { t: 'path', d: 'M3.5 10.6 12 3.6l8.5 7' },
    { t: 'path', d: 'M5.6 9.4V19a1.5 1.5 0 0 0 1.5 1.5h9.8a1.5 1.5 0 0 0 1.5-1.5V9.4' },
    { t: 'path', d: 'M9.8 20.5v-6.2h4.4v6.2' },
  ],
  // 对话气泡：会话 / 售后咨询
  chat: [
    {
      t: 'path',
      d: 'M20.4 11.6a7.6 7.6 0 0 1-11 6.8L4.6 19.8l1.5-4.4a7.6 7.6 0 1 1 14.3-3.8z',
    },
    { t: 'line', x1: 9, y1: 10.4, x2: 15.2, y2: 10.4 },
    { t: 'line', x1: 9, y1: 13.8, x2: 12.8, y2: 13.8 },
  ],
  // 箱子：订单
  box: [
    { t: 'path', d: 'M20.4 8.2 12 3.6 3.6 8.2v7.6L12 20.4l8.4-4.6z' },
    { t: 'path', d: 'M3.6 8.2 12 13l8.4-4.8' },
    { t: 'line', x1: 12, y1: 13, x2: 12, y2: 20.4 },
  ],
  // 小票：我的退款申请
  receipt: [
    { t: 'path', d: 'M6.4 3.8h11.2v16.4l-2.8-1.8-2.8 1.8-2.8-1.8-2.8 1.8z' },
    { t: 'line', x1: 9.4, y1: 8.4, x2: 14.6, y2: 8.4 },
    { t: 'line', x1: 9.4, y1: 12.4, x2: 14.6, y2: 12.4 },
  ],
  // 勾一枚徽章：退款审批
  'check-badge': [
    { t: 'circle', cx: 12, cy: 12, r: 8.4 },
    { t: 'path', d: 'M8.4 12.2l2.6 2.6 4.6-5' },
  ],
  // 剪贴板：审批记录
  clipboard: [
    { t: 'rect', x: 5.4, y: 4.6, w: 13.2, h: 15.6, r: 2 },
    { t: 'path', d: 'M9.2 4.6V3.4a1 1 0 0 1 1-1h3.6a1 1 0 0 1 1 1v1.2' },
    { t: 'line', x1: 8.8, y1: 10.4, x2: 15.2, y2: 10.4 },
    { t: 'line', x1: 8.8, y1: 14.4, x2: 13.2, y2: 14.4 },
  ],
  // 钱包：退款流水（真的打款了）
  wallet: [
    { t: 'rect', x: 3.6, y: 6.4, w: 16.8, h: 12, r: 2.4 },
    { t: 'path', d: 'M3.6 10.4h11.2a2.4 2.4 0 0 1 0 4.8H3.6' },
    { t: 'circle', cx: 17.4, cy: 12.8, r: 0.9 },
  ],
  // 加号：新建会话
  plus: [
    { t: 'line', x1: 12, y1: 5.6, x2: 12, y2: 18.4 },
    { t: 'line', x1: 5.6, y1: 12, x2: 18.4, y2: 12 },
  ],
  // 纸飞机：发送
  send: [
    { t: 'path', d: 'M20.4 3.6 3.8 10.2l6.4 2.6 2.6 6.4z' },
    { t: 'line', x1: 20.4, y1: 3.6, x2: 10.2, y2: 12.8 },
  ],
  // 循环箭头：刷新 / 重试
  refresh: [
    { t: 'path', d: 'M19.6 12a7.6 7.6 0 1 1-2.4-5.6' },
    { t: 'path', d: 'M19.8 4.2v4.6h-4.6' },
  ],
  // 空格箱：没有数据时的空状态
  inbox: [
    { t: 'path', d: 'M3.6 13.2h4.2l1.2 2.2h6l1.2-2.2h4.2' },
    { t: 'path', d: 'M6.6 4.4h10.8l3 8.8v4.4a1.8 1.8 0 0 1-1.8 1.8H5.4a1.8 1.8 0 0 1-1.8-1.8v-4.4z' },
  ],
  // 放大镜：检索依据
  search: [
    { t: 'circle', cx: 10.8, cy: 10.8, r: 6.2 },
    { t: 'line', x1: 15.4, y1: 15.4, x2: 20, y2: 20 },
  ],
  // 时钟：等待处理
  clock: [
    { t: 'circle', cx: 12, cy: 12, r: 8.4 },
    { t: 'path', d: 'M12 7.2V12l3.4 2' },
  ],
  // 人：用户消息头像
  user: [
    { t: 'circle', cx: 12, cy: 8.2, r: 3.4 },
    { t: 'path', d: 'M5.2 19.6a6.8 6.8 0 0 1 13.6 0' },
  ],
  // 机器人：助手消息头像
  robot: [
    { t: 'rect', x: 5.2, y: 7.6, w: 13.6, h: 9.6, r: 2.4 },
    { t: 'line', x1: 12, y1: 3.6, x2: 12, y2: 7.6 },
    { t: 'circle', cx: 12, cy: 4.2, r: 0.7 },
    { t: 'circle', cx: 9.2, cy: 12.4, r: 1 },
    { t: 'circle', cx: 14.8, cy: 12.4, r: 1 },
    { t: 'line', x1: 9.6, y1: 15.4, x2: 14.4, y2: 15.4 },
  ],
}

const props = withDefaults(
  defineProps<{
    name: keyof typeof ICONS | string
    /** 边长（px）。默认 18，跟 13.5px 的正文放在一起不抢戏。 */
    size?: number
  }>(),
  { size: 18 },
)

// 取不到就返回 undefined —— 模板里随之什么都不画，
// 写错名字的结果是"图标没出来"，而不是报错白屏。
const shapes = computed<Shape[]>(() => ICONS[props.name] ?? [])
</script>

<template>
  <svg
    class="icon"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.7"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    <template v-for="(shape, index) in shapes" :key="index">
      <path v-if="shape.t === 'path'" :d="shape.d" />
      <circle v-else-if="shape.t === 'circle'" :cx="shape.cx" :cy="shape.cy" :r="shape.r" />
      <line v-else-if="shape.t === 'line'" :x1="shape.x1" :y1="shape.y1" :x2="shape.x2" :y2="shape.y2" />
      <rect
        v-else
        :x="shape.x"
        :y="shape.y"
        :width="shape.w"
        :height="shape.h"
        :rx="shape.r ?? 0"
        :ry="shape.r ?? 0"
      />
    </template>
  </svg>
</template>

<style scoped>
/* `vertical-align` 必须给：svg 默认是基线对齐，
   和文字并排时会坐得偏下，看着像没对齐。 */
.icon {
  flex-shrink: 0;
  vertical-align: -0.15em;
}
</style>
