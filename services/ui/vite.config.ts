import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
  server: {
    // For local `npm run dev` — proxy /api and /ws to the dev backend.
    port: 5173,
    proxy: {
      '/api': {
        target: 'https://localhost:8443',
        changeOrigin: true,
        secure: false,
      },
      '/ws': {
        target: 'wss://localhost:8443',
        changeOrigin: true,
        ws: true,
        secure: false,
      },
    },
  },
  test: {
    environment: 'happy-dom',
    globals: true,
  },
})
