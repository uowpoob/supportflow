# SupportFlow 前端（web/）

React + TypeScript + Vite。第一步只搭骨架：目录、布局、路由、请求封装、三个基础页面。
业务数据还没接，接口返回空的时候页面显示的是占位内容。

## 跑起来

后端要先在 `127.0.0.1:8000` 起着（项目根目录执行 `.venv/Scripts/supportflow.exe`），然后：

```bash
cd web
npm install          # 第一次
npm run dev          # http://127.0.0.1:5173
```

其他命令：

```bash
npm run typecheck    # 只做类型检查，不起服务
npm run build        # 类型检查 + 打包到 dist/
npm run preview      # 预览打包结果
```

## 页面地址 vs 接口地址

这两类地址刻意分开，别混：

| 类型 | 例子 | 谁处理 |
| --- | --- | --- |
| 前端页面路由 | `/login`、`/customer`、`/admin`、`/admin/orders` | Vite dev server（或生产环境的静态托管） |
| 后端数据接口 | `/api/login`、`/api/admin/orders` | 由 `vite.config.ts` 里的 proxy 转发到 FastAPI |

浏览器里只会看到 `127.0.0.1:5173` 这一个源，`/api` 是开发服务器帮你转发的。
所以**后端不需要开 CORS**，将来加 Cookie 也不会遇到跨域 Cookie 的麻烦。

转发规则写在 `vite.config.ts`：`/api/login` → `http://127.0.0.1:8000/login`
（后端路由本身不带 `/api` 前缀，所以转发时把 `/api` 去掉了）。
要改后端地址就设 `VITE_API_BASE_URL`，不必动代码。

## 目录结构

```
web/src/
├─ api/
│  ├─ client.ts       统一 fetch 封装：拼地址、带 Cookie、解析 {code,message,data} 信封、把错误压成人话
│  ├─ auth.ts         POST /login、GET /me（待后端实现）、logout
│  ├─ customer.ts     客户侧接口
│  └─ admin.ts        管理侧接口
├─ auth/
│  ├─ AuthContext.tsx 当前登录用户（signIn / signOut）
│  ├─ guards.tsx      路由守卫：RequireAuth、RequireRole
│  └─ paths.ts        角色 → 首页路径（只定义一次）
├─ layouts/AppLayout.tsx  顶部导航 + 当前用户 + 退出按钮
├─ pages/             登录页、客户首页、管理员首页/订单/退款审批、403、404
├─ styles/global.css  全部样式（CSS 变量 + 语义化类名，没引 UI 库）
├─ App.tsx            路由表
├─ main.tsx           入口
└─ types.ts           与后端 schema 对应的类型
```

## 三条要记住的约定

1. **页面里不直接写 `fetch`。** 一律走 `src/api/`，否则错误处理要重复写很多遍。
2. **类型跟着后端 schema 走。** `types.ts` 里的字段名与 `src/supportflow/schemas/*.py` 一一对应，后端改字段这里同步改。
3. **前端守卫不是安全边界。** `RequireRole` 只是不让人误入别人的页面；谁都能用 curl 直接调接口。真正的拦截必须在后端每个接口上做。

## 现在的状态与缺口

已经做完：

- 路由骨架：`/`（按角色分流）、`/login`、`/customer`、`/admin`、`/admin/orders`、`/admin/refunds`、404
- 登录页调真实接口 `POST /api/login`，成功后按 `role` 跳到 `/customer` 或 `/admin`；失败显示后端返回的原因，422 会逐字段列出
- 管理员两个列表页会真的发请求，把后端原始返回打出来（用来确认链路通不通）
- 退出按钮清本地状态并回登录页

还没做（按顺序）：

| # | 事项 | 说明 |
| --- | --- | --- |
| 1 | 后端下发会话 Cookie | 后端加 `Set-Cookie`（HttpOnly）+ `GET /me`，前端初始化时向服务端问"我是谁" |
| 2 | 刷新保持登录 | 现在靠 `sessionStorage` 记着（见 `AuthContext.tsx` 顶部注释），换成服务端会话后删掉 |
| 3 | 真正的退出 | 后端加 `POST /logout`，现在只是清前端状态 |
| 4 | 后端接口鉴权 | `/admin/*` 现在没有鉴权，谁都能调 |
| 5 | 审批对象改为申请编号 | 现在是 `POST /admin/deal_refund_approvals/{order_id}`，应改成退款申请编号 |
| 6 | 对话与会话列表 | 等 Agent + 会话接口；SSE 断线重连后不能重复执行业务操作 |
