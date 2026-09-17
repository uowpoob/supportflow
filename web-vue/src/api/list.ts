import type { JsonRecord, ListResult, PageQuery } from '../types'

/** 可能是"列表"的字段名，按优先级依次尝试。后端分页结构定稿后这里只会剩一个。 */
const LIST_KEYS = ['items', 'list', 'records', 'rows', 'results', 'data']
const TOTAL_KEYS = ['total', 'count', 'total_count']

/**
 * 把后端各式各样的列表返回压成统一形状，页面只认 `items`。
 * 三种都认不出来时给空列表，**不抛错** —— "结构还不一样"不该由页面来兜。
 */
export function normalizeList(raw: unknown): ListResult {
  if (Array.isArray(raw)) {
    return { items: raw as JsonRecord[], raw }
  }
  if (raw !== null && typeof raw === 'object') {
    const obj = raw as Record<string, unknown>
    for (const key of LIST_KEYS) {
      if (Array.isArray(obj[key])) {
        return { items: obj[key] as JsonRecord[], total: readTotal(obj), raw }
      }
    }
  }
  return { items: [], raw }
}

function readTotal(obj: Record<string, unknown>): number | undefined {
  for (const key of TOTAL_KEYS) {
    const value = obj[key]
    if (typeof value === 'number') return value
  }
  return undefined
}

/** 拼分页查询串；只带真正传了的参数，避免出现 `?offset=undefined`。 */
export function pageQuery(query: PageQuery): string {
  const params = new URLSearchParams()
  if (query.offset !== undefined) params.set('offset', String(query.offset))
  if (query.limit !== undefined) params.set('limit', String(query.limit))
  const suffix = params.toString()
  return suffix ? `?${suffix}` : ''
}

/** 路径参数统一编码，避免编号里有特殊字符时把地址拼坏。 */
export function encodeParam(value: string): string {
  return encodeURIComponent(value)
}
