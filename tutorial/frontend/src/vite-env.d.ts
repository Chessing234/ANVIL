/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_WS_URL?: string;
  readonly VITE_SANDBOX_WS_URL?: string;
  readonly VITE_LEARN_WS_URL?: string;
  readonly VITE_API_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
