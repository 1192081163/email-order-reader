import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  root: "electron/renderer",
  base: "./",
  build: {
    outDir: "../../dist-renderer",
    emptyOutDir: true,
  },
  test: {
    globals: true,
    environment: "jsdom",
    include: ["../../tests/electron/**/*.test.ts", "../../tests/electron/**/*.test.tsx"],
  },
});
