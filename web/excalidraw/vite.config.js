import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "./",
  plugins: [react()],
  build: {
    emptyOutDir: true,
    outDir: "../../src/natureai_next/resources/excalidraw",
    sourcemap: false,
  },
});
