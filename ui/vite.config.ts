import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

// Strict Content Security Policy for production builds. Log text in the UI is untrusted, so
// the page allows no inline or third-party scripts. Inline styles are needed by Radix and Recharts.
const CSP = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self'",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'none'",
].join('; ')

const csp = (): Plugin => ({
  name: 'signal-room-csp',
  apply: 'build',
  transformIndexHtml: (html) =>
    html.replace('<head>', `<head>\n    <meta http-equiv="Content-Security-Policy" content="${CSP}" />`),
})

// `base` lets the replay build live under a GitHub Pages project path (/Signal-room/).
export default defineConfig({
  base: process.env.VITE_BASE ?? '/',
  plugins: [react(), tailwindcss(), csp()],
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, './src') },
  },
})
