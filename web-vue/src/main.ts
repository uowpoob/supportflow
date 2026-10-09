import { createApp } from 'vue'

import App from './App.vue'
import { restoreSession } from './auth/useAuth'
import { router } from './router'
import './styles/global.css'
import './styles/workspace.css'

// 启动就向服务端确认身份（"我手上这张 Cookie 是谁的？"）。
// 这里不 await：路由守卫会 await 同一个 Promise，两处只会发一次 `/me`。
void restoreSession()

const app = createApp(App)
app.use(router)
app.mount('#root')
