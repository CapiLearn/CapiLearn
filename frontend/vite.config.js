import process from "node:process";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  const apiBaseUrl = env.VITE_API_BASE_URL?.trim();

  if (command === "build" && !apiBaseUrl) {
    throw new Error(
      "VITE_API_BASE_URL is required for production frontend builds."
    );
  }

  return {
    plugins: [react()],
  };
});