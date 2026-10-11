import { readFile } from 'node:fs/promises'
import { defineConfig, loadEnv, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
// @ts-expect-error The server renderer is plain JavaScript.
import { renderHtml } from './server/metadata.mjs'
// @ts-expect-error The server pipeline is plain JavaScript.
import { websiteMiddleware } from './server/middleware.mjs'

export default defineConfig(({ mode }) => {
  const environment = { ...loadEnv(mode, process.cwd(), ['MOSS_', 'SITE_']), ...process.env }
  const content: Plugin = {
    name: 'moss-website-content',
    configureServer(server) {
      server.middlewares.use(websiteMiddleware(environment, async (website: unknown, page: unknown) => {
        const template = await server.transformIndexHtml('/', await readFile('index.html', 'utf8'))
        return renderHtml(template, website, page, environment)
      }))
    },
    configurePreviewServer(server) {
      server.middlewares.use(websiteMiddleware(environment, async (website: unknown, page: unknown) =>
        renderHtml(await readFile('dist/index.html', 'utf8'), website, page, environment)))
    },
  }
  return { plugins: [react(), content], server: { fs: {allow:['..']}, port: 5174, strictPort: true }, preview: { port: 5174, strictPort: true } }
})
