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

/** 分页入参，对齐后端 `?offset=&limit=` */
export interface PageQuery {
  offset?: number
  limit?: number
}

/**
 * 后端业务接口目前都返回空信封（`return result.success()`），字段还没定下来。
 * 所以先用"任意键值对"承载，等响应结构定稿再补具体类型 ——
 * 现在编字段名只会白写一遍，后端一改就全错。
 */
export type JsonRecord = Record<string, unknown>

/**
 * 列表接口的统一形状。
 * 后端分页结构没定，先容忍三种返回：数组 / 对象里带 items|list|records / 其它。
 * 认不出来就是空列表，页面再把原始 JSON 折叠出来供核对。
 */
export interface ListResult {
  items: JsonRecord[]
  total?: number
  /** 接口的原始返回，不加工，方便对着它核对字段。 */
  raw: unknown
}
