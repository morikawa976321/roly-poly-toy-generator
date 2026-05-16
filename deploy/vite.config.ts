import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import wasm from "vite-plugin-wasm";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const coreSrc = path.resolve(__dirname, "../frontend/src");

export default defineConfig({
  plugins: [react(), tailwindcss(), wasm()],
  resolve: {
    alias: {
      "@core": coreSrc,
    },
  },
  optimizeDeps: {
    exclude: ["opencascade.js"],
  },
});
