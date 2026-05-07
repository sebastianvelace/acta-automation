import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    // Evita ENOSPC ("System limit for number of file watchers reached") en Linux
    // cuando coexiste con uvicorn --reload y muchos inotify.
    watch: {
      usePolling: true,
      interval: 1000,
    },
  },
});
