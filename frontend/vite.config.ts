import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

// The dev server proxies /api to the backend rather than the app calling
// http://localhost:8000 directly. That is not a convenience: the refresh cookie is
// scoped to /api/v1/auth and set without SameSite=None, and /auth/refresh rejects a
// request whose Origin it cannot verify. Talking to a second origin in development
// would mean the cookie silently never arrives, and the bug would only appear in
// the one flow nobody tests by hand. Production does the same rewrite at the static
// host, so development and production differ in configuration but not in shape.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
    },
  },
  build: {
    // Sourcemaps make a production stack trace readable without shipping the
    // original source in the bundle itself.
    sourcemap: true,
  },
})
