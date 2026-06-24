import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: path.resolve(__dirname, "../relocation_jobs/static/dist"),
    emptyOutDir: true,
    rollupOptions: {
      input: path.resolve(__dirname, "src/main.jsx"),
      output: {
        entryFileNames: "board.js",
        chunkFileNames: "board-[name].js",
        assetFileNames: "board-[name][extname]",
      },
    },
  },
  base: "/static/dist/",
});
