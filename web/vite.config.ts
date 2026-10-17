import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api/hermes": {
        target: process.env.HERMES_TARGET || process.env.API_TARGET || "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/api/health": {
        target: process.env.API_TARGET || "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: () => "/health",
      },
      "/api/ai": {
        target: process.env.API_TARGET || "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/api": {
        target: process.env.API_TARGET || "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
