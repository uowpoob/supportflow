import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// 前端页面地址是 /login、/customer、/admin；后端数据接口统一走 /api/**。
// 开发期由 Vite 把 /api 代理到 FastAPI，浏览器只看到同一个源，
// 因此不需要后端开 CORS，也不会有跨域 Cookie 的问题。
//
// ⚠️ 端口用 5174，不是 5173 —— React 版（web/）占着 5173，
// 两个 dev server 同时跑时端口不能撞（`strictPort: true` 撞了会直接启动失败）。
// ⚠️ 临时：8000 被 Windows 端口保留段占着绑不上，后端改跑 8080。
// 等 `net stop winnat && net start winnat` 修好 8000，把这里改回 8000 即可。
const BACKEND = 'http://127.0.0.1:8080'

export default defineConfig({
  plugins: [vue()],
  server: {
    // 显式绑 IPv4：默认值在 Windows 上只监听 [::1]，
    // 会导致 http://127.0.0.1:5174 连不上（只有 localhost 能开）
    host: '127.0.0.1',
    port: 5174,
    strictPort: true,
    proxy: {
      '/api': {
        target: BACKEND,
        changeOrigin: true,
        // 后端路由本身不带 /api 前缀（例如 POST /login），
        // 所以转发前把 /api 去掉：/api/login -> http://127.0.0.1:8000/login
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
