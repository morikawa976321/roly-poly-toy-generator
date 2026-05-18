/**
 * Vite ビルド・開発サーバー設定。
 *
 * 役割: React + Tailwind + WASM のフロントエンド bundler 設定。
 * 働き: dev 時 port 5173、/api を backend :8000 にプロキシ。opencascade.js と pyodide を optimizeDeps 除外。
 */
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import wasm from "vite-plugin-wasm";

export default defineConfig({
  plugins: [react(), tailwindcss(), wasm()],
  optimizeDeps: {
    exclude: ["opencascade.js", "pyodide"],
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
