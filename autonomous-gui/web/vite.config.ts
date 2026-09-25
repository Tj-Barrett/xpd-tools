/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// `npm run dev` proxies API calls to the server (xpd-autonomous-server <config>).
export default defineConfig({
  plugins: [react()],
  // `@/x` imports resolve to src/x, as in finch.
  resolve: { alias: { '@': '/src' } },
  server: {
    proxy: { '/api': 'http://127.0.0.1:8765' },
  },
  // Same test setup as finch: `npm test` runs src/testing/tests with Vitest in jsdom.
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/testing/setup.ts'],
    globals: true,
  },
})
