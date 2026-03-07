import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Produces a self-contained server.js for Docker
  output: "standalone",
};

export default nextConfig;
