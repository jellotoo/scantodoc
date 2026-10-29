import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The built app goes into the Python package, so `scantodoc serve` can serve it
// without Node. During development, `npm run dev` proxies the API to a running
// `scantodoc serve --no-browser`.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "../src/scantodoc/web/static",
    emptyOutDir: true,
    chunkSizeWarningLimit: 900,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/fonts": "http://127.0.0.1:8765",
    },
  },
});
