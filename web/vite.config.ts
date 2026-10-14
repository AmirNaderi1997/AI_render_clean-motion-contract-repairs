import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api/hermes": {
        target: process.env.HERMES_TARGET || process.env.API_TARGET || "http://localhost",
        changeOrigin: true,
      },
      "/api/health": {
        target: process.env.API_TARGET || "http://localhost",
        changeOrigin: true,
      },
      "/api/ai": {
        target: process.env.API_TARGET || "http://localhost",
        changeOrigin: true,
      },
      "/api": {
        target: process.env.API_TARGET || "http://localhost",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
