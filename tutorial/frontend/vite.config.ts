import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/** GitHub project pages need ``/<repo>/``; user pages (``*.github.io`` repo) use ``/``. */
function normalizeBase(raw: string | undefined): string {
  const p = raw?.trim();
  if (!p || p === "/") return "/";
  const withLeading = p.startsWith("/") ? p : `/${p}`;
  return withLeading.endsWith("/") ? withLeading : `${withLeading}/`;
}

export default defineConfig({
  base: normalizeBase(process.env.VITE_BASE_PATH),
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
