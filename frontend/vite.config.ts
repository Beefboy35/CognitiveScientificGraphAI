import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    watch: {
      usePolling: true,
    },
    allowedHosts: ['kb.studyninja.ru', 'kb.xteam.pro', 'dev.kb.studyninja.ru', 'dev.kb.xteam.pro'],
    proxy: {
      '/v1': {
        target: 'http://fastapi-dev:8000',
        changeOrigin: true,
        secure: false,
      },
      '/ws': {
        target: 'ws://fastapi-dev:8000',
        ws: true,
        changeOrigin: true,
        secure: false,
      },
      '/health': {
        target: 'http://fastapi-dev:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  }
})
