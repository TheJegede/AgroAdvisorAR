import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.ico', 'favicon-96x96.png', 'apple-touch-icon.png', 'favicon.svg', 'icons.svg'],
      manifest: {
        name: 'AgroAdvisor AR',
        short_name: 'AgroAdvisor',
        description: 'Arkansas crop & livestock advisory — rice, soybean, poultry.',
        theme_color: '#1f3a26',
        background_color: '#f4efe2',
        display: 'standalone',
        start_url: '/',
        icons: [
          { src: '/favicon-96x96.png', sizes: '96x96', type: 'image/png' },
          { src: '/apple-touch-icon.png', sizes: '180x180', type: 'image/png' },
          { src: '/web-app-manifest-192x192.png', sizes: '192x192', type: 'image/png', purpose: 'maskable' },
          { src: '/web-app-manifest-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
          { src: '/icons.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any maskable' },
        ],
      },
      workbox: {
        // Precache the app shell only. Do NOT runtime-cache /api/* — advisory
        // responses must never be auto-served offline (safety: stale rates).
        globPatterns: ['**/*.{js,css,html,svg,woff2}'],
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//],
      },
      // Inject the manifest link + SW in dev too, so the installable metadata is
      // present when running `npm run dev` (e.g. under Playwright). Prod is
      // unaffected.
      devOptions: {
        enabled: true,
      },
    }),
  ],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    exclude: ['e2e/**', 'node_modules/**', 'dist/**'],
  },
})
