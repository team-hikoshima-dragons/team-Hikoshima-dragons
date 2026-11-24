import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/static/',
  server: {
    proxy: {
      '/api': 'http://web:8000',          // Djangoコンテナへ転送
    },
    watch: {
      usePolling: true,                   // C:\ に置いてるとファイル変更が届かないため
    },
  },
})