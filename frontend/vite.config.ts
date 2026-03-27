import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5175,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''), // /api/documents/upload -> /documents/upload
      },
      // Entity Extractor (OOCP Text Body Extractor) - runs on 5001
      '/ee': {
        target: 'http://localhost:5001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/ee/, ''), // /ee/api/analyze -> /api/analyze
      },
    },
  },
})
