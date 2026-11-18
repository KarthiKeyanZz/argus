import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The API stays on 127.0.0.1:8000; the dev server proxies /api to it, so the browser
// talks to a single origin. The backend's Origin guard allows http://localhost:5173.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": new URL("./src", import.meta.url).pathname } },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } },
  },
  test: { environment: "jsdom", include: ["src/**/*.test.{ts,tsx}"] },
});
