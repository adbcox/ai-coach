import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev: `npm run dev` proxies /api to a locally running backend on the default port.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://localhost:26219" } },
});
