import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The production build is served by `idt serve` from src/idt/server/web_dist.
export default defineConfig({
  plugins: [react()],
  build: { outDir: "../../src/idt/server/web_dist", emptyOutDir: true },
  server: { port: 5173, proxy: { "/api": "http://localhost:8742" } },
});
