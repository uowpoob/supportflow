/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 后端地址。默认走 vite.config.ts 里的 /api 代理，一般不需要设置。 */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
