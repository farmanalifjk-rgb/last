import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';

// The backend origin is only used by the dev/preview proxy, never by browser code.
// Override with BACKEND_URL when the API runs somewhere other than the default.
const backend = process.env.BACKEND_URL || 'http://127.0.0.1:8000';

const proxy = {
  target: backend,
  changeOrigin: true,
};

export default defineConfig({
  build: {
    // Multi-page build: receipt.html is opened in a separate window by the POS
    // (window.open('/receipt.html?...')), so it must be emitted to dist/ too.
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL('./index.html', import.meta.url)),
        receipt: fileURLToPath(new URL('./receipt.html', import.meta.url)),
      },
    },
  },
  server: {
    // Allow the sandbox preview host (a leading dot matches any subdomain of e2b.app).
    allowedHosts: ['localhost', '.e2b.app'],
    proxy: {
      '/api': proxy,
      '/media': proxy,
    },
  },
  preview: {
    proxy: {
      '/api': proxy,
      '/media': proxy,
    },
  },
});
