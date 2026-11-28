import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 개발 중에는 프론트(5173)에서 백엔드(8000)로 프록시한다.
// 배포 시에는 같은 오리진에 올리거나 VITE_API_BASE 로 지정한다.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
