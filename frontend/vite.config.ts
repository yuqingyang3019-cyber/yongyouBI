import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    include: ["@univerjs/presets", "@univerjs/preset-sheets-core"]
  },
  server: {
    host: true,
    proxy: {
      "/api": "http://localhost:8000",
      "/health": "http://localhost:8000"
    }
  },
  preview: {
    host: true,
    proxy: {
      "/api": "http://localhost:8000",
      "/health": "http://localhost:8000"
    }
  }
});
