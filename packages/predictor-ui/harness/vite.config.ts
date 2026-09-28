import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss() as any],
  // Two copies of React, and hooks throw "Cannot read properties of null". The
  // harness has its own node_modules (so a build tool here can never disturb the
  // library's) but the components it renders resolve `react` from the parent's.
  // Dedupe points both at one instance; the alternative was a blank page and a
  // console error, which is exactly the failure a screenshot cannot explain.
  resolve: { dedupe: ["react", "react-dom"] },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    // Both pages: the states, and the 390px frame that measures them at a width
    // headless Chrome will not open a window at.
    rollupOptions: {
      input: { states: "index.html", narrow: "narrow.html" },
    },
  },
  preview: { port: 4180, host: true },
});
