import { defineConfig } from 'vite'
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// The FastAPI engine wrapper. Port 8001 (not 8000) because 8000 falls in a Windows WinNAT
// excluded port range on this WSL2 host and is unbindable. Override with API_PROXY_TARGET.
const API_TARGET = process.env.API_PROXY_TARGET || 'http://127.0.0.1:8001'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: true,        // expose the dev server on the LAN (phone access); proxy keeps one origin
    port: 5173,
    strictPort: true,
    // One origin in the browser: the SPA and /api share http://localhost:5173, so there is no
    // CORS surface and no auth handshake — the engine wrapper is reached purely via this proxy.
    proxy: {
      '/api': { target: API_TARGET, changeOrigin: true },
    },
  },
})
