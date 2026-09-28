import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      injectRegister: "script-defer",
      manifestFilename: "manifest.webmanifest",
      useCredentials: true,
      pwaAssets: {
        image: "public/favicon.svg",
        preset: "minimal-2023",
        includeHtmlHeadLinks: true,
        overrideManifestIcons: true,
      },
      manifest: {
        id: "/",
        name: "Finanças Pessoais",
        short_name: "Finanças",
        description: "Painel financeiro pessoal e privado",
        lang: "pt-BR",
        start_url: "/",
        scope: "/",
        display: "standalone",
        background_color: "#090c10",
        theme_color: "#0d1117",
      },
      workbox: {
        globPatterns: ["assets/**/*.{js,css}", "**/*.{png,svg,ico}"],
        navigateFallback: null,
        runtimeCaching: [],
        cleanupOutdatedCaches: true,
        clientsClaim: true,
        skipWaiting: true,
      },
    }),
  ],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
  },
});
