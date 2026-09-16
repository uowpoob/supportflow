# 登录流程：从密码验证到会话 Cookie

当前已实现 `POST /login` 的输入校验、账号密码验证、会话写入、Cookie 下发。
`GET /me`、后端权限检查、`POST /logout` 尚未实现，前端刷新仍暂用 sessionStorage。

## 请求怎么经过各层

1. 前端向 `/api/login` 提交 username、password；Vite 代理为后端 `/login`。
2. `schemas/login.py` 的 `LoginRequest` 校验输入：用户名长度 1～64 且不能全空白，密码不为空且 UTF-8 编码不超过 72 字节，多余字段拒绝。输入非法返回 422，尚不查询数据库。
3. `api/login.py` 通过 `Depends(get_db)` 得到本次请求的数据库会话，调用 `services/login.py` 中的 `authenticate_user`。
4. 服务按用户名查 users，使用 bcrypt 核对输入密码与 password_hash，并检查 is_active。密码计算放在线程中，避免阻塞异步事件循环。用户不存在、密码错误或账号停用都返回同样的 401，不创建新会话。
5. API 构造 `LoginResponse`，只选取 id、username、role，避免返回密码哈希。
6. `create_login_session` 调用 `secrets.token_urlsafe(32)` 生成 32 字节安全随机数的 URL 安全编码，通常是 43 个字符；每次登录重新生成。token 不包含用户信息，也不是 JWT。
7. 计算 token 的 SHA-256 十六进制摘要（64 字符），连同用户 ID 和 UTC 过期时间写入 auth_sessions。密码继续使用 bcrypt，不能换成这里的 SHA-256。
8. `await db.commit()` 成功后才返回 token。若提交失败则 rollback 并抛出异常，接口不会下发新的 Cookie，也不会返回成功。
9. API 调用 `response.set_cookie()` 下发原始 token，再返回 `Success[LoginResponse]` JSON。响应声明 `response_model`，FastAPI 对完整成功响应进行校验和序列化，接口文档也能显示明确结构。

## 响应的两部分

响应头的 `Set-Cookie` 用于交给浏览器保存凭证。响应体仍为：

```json
{"code":"200","message":"ok","data":{"id":1,"username":"示例用户","role":"customer"}}
```

token 原文和哈希都不放进 JSON。`Cache-Control: no-store` 要求不缓存登录响应。

Cookie 名称为 `supportflow_session`：

| 属性 | 当前设置和用途 |
| --- | --- |
| HttpOnly | JavaScript 不能通过 document.cookie 读取凭证，浏览器仍会随匹配请求发送 |
| SameSite | Lax，限制部分跨站请求携带 Cookie；并不替代完整的 CSRF 防护 |
| Path | `/`，覆盖当前应用路径 |
| Domain | 不设置，限定当前主机 |
| Max-Age / Expires | 根据会话有效期设置；默认 24 小时 |
| Secure | 本地 HTTP 默认关闭，生产 HTTPS 必须开启 |

前端请求封装已经设置 `credentials: 'include'`，不需要手动读取或保存 token。

## 配置

`core/auth.py` 独立读取环境变量或项目 `.env`，不依赖模型服务密钥：

```dotenv
SESSION_TTL_SECONDS=86400
SESSION_COOKIE_SECURE=false
```

生产 HTTPS 将 `SESSION_COOKIE_SECURE` 改为 `true`，修改配置后重启后端。
数据库的 expires_at 是后续认证的判断依据，不能只依赖浏览器的 Cookie 到期删除行为。
现阶段退出按钮只清前端状态，尚不会撤销服务端会话；完成 `/logout` 后才具备真正退出能力。

## 验证范围

`tests/test_login.py` 用真实 HTTP 路由及密码校验、模拟数据库访问，覆盖成功登录、未知用户、错误密码、禁用账号、非法输入、提交失败、不同登录生成不同 token、Cookie 属性和响应文档结构。
现有模型测试验证会话表约束。另已通过临时账号执行真实 MySQL 与 ASGI HTTP 客户端联调，验证成功响应、Cookie 保存、会话哈希及用户关联；临时数据由外层事务回滚。该联调不等于浏览器界面测试。

运行自动化测试：

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
```
