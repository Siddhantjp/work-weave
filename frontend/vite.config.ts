import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The backend serves the built app at /static (assets) and / (index.html).
export default defineConfig({
  plugins: [react()],
  base: "/static/",
  server: { proxy: { "/api": "http://localhost:8000" } },
  build: { outDir: "dist", sourcemap: false },
});
