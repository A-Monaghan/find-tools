/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
  /** OOCP Entity Extractor public URL in prod (dev uses Vite /ee proxy). */
  readonly VITE_ENTITY_EXTRACTOR_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
