# SupportFlow 前端（web/）

React + TypeScript + Vite。前后端分离：后端只提供 JSON 接口，前端只负责界面。

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
| 前端页面路由 | `/login`、`/customer/orders`、`/admin/refunds` | Vite dev server（或生产环境的静态托管） |
| 后端数据接口 | `/api/login`、`/api/admin/orders` | 由 `vite.config.ts` 里的 proxy 转发到 FastAPI |

浏览器里只会看到 `127.0.0.1:5173` 这一个源，`/api` 是开发服务器帮你转发的。
所以**后端不需要开 CORS**，Cookie 也不会遇到跨域问题。

转发规则写在 `vite.config.ts`：`/api/login` → `http://127.0.0.1:8000/login`
（后端路由本身不带 `/api` 前缀，所以转发时把 `/api` 去掉了）。
要改后端地址就设 `VITE_API_BASE_URL`，不必动代码。

## 目录结构

```
web/src/
├─ api/
│  ├─ client.ts       统一 fetch 封装：拼地址、带 Cookie、解析信封、把错误压成人话
│  ├─ list.ts         列表返回归一化（后端的三种可能形状都认）+ 分页查询串
│  ├─ auth.ts         POST /login、POST /logout、GET /me
│  ├─ customer.ts     客户侧接口
│  └─ admin.ts        管理侧接口
├─ auth/
│  ├─ AuthContext.tsx 当前登录用户（启动时问 /me，含 initializing 三态）
│  ├─ guards.tsx      路由守卫：RequireAuth、RequireRole、AuthLoading
│  └─ paths.ts        角色 → 首页路径（只定义一次）
├─ components/        公共零件
│  ├─ Async.tsx               加载中 / 失败可重试 / 空状态 / 待实现说明 / 原始返回
│  ├─ DataTable.tsx           表格（列可由数据自动推导）
│  ├─ KeyValueList.tsx        JSON 对象 → 键值表
│  ├─ Pager.tsx               分页条
│  ├─ ResourceListPage.tsx    列表页骨架：请求 → 四态 → 分页 → 原始返回
│  ├─ ResourceDetailPage.tsx  详情页骨架（含 AsyncSection 附加区块）
│  └─ value.tsx               值的显示规则
├─ hooks/useApi.ts    发一次请求 + 管 loading/done/error 三态
├─ layouts/AppLayout.tsx  顶部导航 + 当前用户 + 退出按钮
├─ pages/             见下表
├─ styles/global.css  全部样式（CSS 变量 + 语义化类名，没引 UI 库）
├─ App.tsx            路由表
├─ main.tsx           入口
└─ types.ts           与后端 schema 对应的类型
```

## 页面与对应接口

| 页面路由 | 调用的接口 | 说明 |
| --- | --- | --- |
| `/login` | `POST /login` | 成功后按 `role` 跳 `/customer` 或 `/admin` |
| `/customer` | `GET /customer/conversations` | 售后首页：快捷入口 + 会话列表 + 对话区（Agent 未接） |
| `/customer/orders` | `GET /customer/orders` | 我的订单列表 |
| `/customer/orders/:orderNo` | `GET /customer/orders/{order_no}`、`.../refund-eligibility` | 详情 + 只读的退款资格判定 |
| `/customer/refund-requests` | `GET /customer/refund-requests` | 我的申请列表 |
| `/customer/refund-requests/:requestKey` | `GET /customer/refund-requests/{request_key}` | 申请进度 |
| `/admin` | — | 概览与四个入口 |
| `/admin/orders` | `GET /admin/orders` | 全部订单 |
| `/admin/orders/:orderNo` | `GET /admin/orders/{order_no}` | 订单详情 |
| `/admin/refunds` | `GET /admin/refund-requests` | 待办：`status='pending'` 的申请 |
| `/admin/refunds/:requestKey` | `GET /admin/refund-requests/{request_key}` | 申请详情 + 审批区（按钮禁用） |
| `/admin/refund-approvals` | `GET /admin/refund-approvals` | 审批记录（审计） |
| `/admin/refund-records` | `GET /admin/refund-records` | 退款执行流水 |

**写操作还没打开**：`POST /customer/refund-requests`（提交申请）与
`POST /admin/refund-requests/{request_key}/decision`（批准 / 拒绝）在界面上留了位置、按钮禁用，
等后端请求体定稿再启用。对应函数已经在 `api/customer.ts`、`api/admin.ts` 里写好了。

## 四条要记住的约定

1. **页面里不直接写 `fetch`。** 一律走 `src/api/`，否则错误处理要重复写很多遍。
2. **类型跟着后端 schema 走。** 后端字段定稿后同步改 `types.ts`，前端不自己造字段。
   现在接口返回的是空信封，所以列表用 `ListResult`、详情用 `JsonRecord` 临时承载。
3. **前端守卫不是安全边界。** `RequireRole` 只是不让人误入页面的"体验"；
   谁都能用 curl 直接调接口。真正的拦截必须在后端每个接口上做。
4. **身份不写在请求里。** 前端从不传 `user_id`，后端只认 Cookie。
   这是"看不到别人的订单"的前提。

## 现在的状态

已完成：登录 / 退出 / 恢复身份（后端下发 HttpOnly Cookie，前端启动时问 `/me`）、
角色分流与 403、以及上表全部读取类页面的接线。

后端 14 条业务接口**目前都是 `return result.success()` 的空壳**：没有业务逻辑，
业务表也没有数据。所以这些页面现在统一显示"没有数据"的空状态，
并在下方折叠展示接口原始返回，方便对着字段继续开发。

还没做：

| # | 事项 |
| --- | --- |
| 1 | 后端给 `/admin/**`、`/customer/**` 挂鉴权（现在零鉴权，任何人可调） |
| 2 | 业务逻辑：退款资格判定、订单查询、审批写入 |
| 3 | 数据可复现：`scripts/seed.py`（现在业务表 0 行） |
| 4 | 写操作界面：提交退款申请表单、批准 / 拒绝按钮 |
| 5 | 对话区接 Agent 与 SSE 流式输出 |
