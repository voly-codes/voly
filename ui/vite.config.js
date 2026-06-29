import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

const apiPort = process.env.CODEOPS_UI_API_PORT ?? '7788'

export default defineConfig({
  plugins: [svelte()],
  build: {
    outDir: '../codeops/web/static',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${apiPort}`,
        changeOrigin: true,
      },
    },
  },
})
