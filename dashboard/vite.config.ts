import fs from "node:fs";
import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  base: "/qa-api-monitor/",
  plugins: [
    react(),
    tailwindcss(),
    {
      name: "serve-sample-history-in-dev",
      apply: "serve",
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          const urlPath = req.url?.split("?")[0] ?? "";
          if (
            urlPath === "/qa-api-monitor/history.json" ||
            urlPath === "/history.json"
          ) {
            const samplePath = path.resolve(
              import.meta.dirname,
              "sample-history.json",
            );
            if (fs.existsSync(samplePath)) {
              res.setHeader("Content-Type", "application/json; charset=utf-8");
              res.setHeader("Cache-Control", "no-store");
              res.end(fs.readFileSync(samplePath, "utf-8"));
              return;
            }
          }
          next();
        });
      },
    },
  ],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/test-setup.ts",
  },
});
