import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 8300,
    proxy: {
      '/api': {
        target: 'http://localhost:8301',
        changeOrigin: true,
      },
    },
  },
})
