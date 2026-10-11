import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

const backendUrl = process.env.VITE_BACKEND_URL || 'http://localhost:8001'

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': '/src' } },
  server: {
    fs: { allow: ['..'] },
    proxy: Object.fromEntries(
      ['/graphql', '/delivery', '/api', '/auth', '/media', '/ready', '/health'].map((path) => [
        path,
        backendUrl,
      ])
    ),
  },
  test: { environment: 'jsdom', include: ['src/**/*.test.{ts,tsx}'], globals: true },
})
