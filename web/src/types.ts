/** 与后端接口一一对应的类型定义。
 *  改后端 schema 时，这里同步改 —— 前端不自己造字段。 */

/** 与后端 `models/enums.py::UserRole` 保持一致 */
export type UserRole = 'customer' | 'admin'

/** 对齐后端 `schemas/login.py::LoginRequest` */
export interface LoginPayload {
  username: string
  password: string
}

/** 对齐后端 `schemas/login.py::LoginResponse` */
export interface CurrentUser {
  id: number
  username: string
  role: UserRole
}

/** 分页入参，对齐后端 `GET /admin/orders?offset=&limit=` */
export interface PageQuery {
  offset?: number
  limit?: number
}
