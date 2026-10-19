import { svelte } from '@sveltejs/vite-plugin-svelte'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [svelte()],
  server: {
    // In development the API runs separately on port 8000; in production FastAPI serves both.
    proxy: { '/api': 'http://localhost:8000' },
  },
})
