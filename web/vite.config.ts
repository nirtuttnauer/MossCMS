import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': '/src' } },
  server: { fs: { allow: ['..'] }, proxy: Object.fromEntries(['/graphql', '/delivery', '/api', '/auth', '/media', '/ready', '/health'].map(path => [path, 'http://localhost:8000'])) },
  test: { environment: 'jsdom', include: ['src/**/*.test.tsx'], globals: true },
})
