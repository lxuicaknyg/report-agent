import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [vue()],
    server: {
      port: 5173,
      proxy: {
        // The whole /api tree, not just this app's slice: a contributed module
        // developed against its own backend sets VITE_API_PROXY_TARGET and its
        // /api/<tool>/v1/* calls need to be proxied too.
        "/api": {
          target: env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000",
          changeOrigin: true,
        },
      },
    },
  };
});
