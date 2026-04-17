import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// GreenPulse 대시보드 — Vite 설정
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // FastAPI 백엔드로 API 프록시
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
});
