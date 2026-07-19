import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Pin the workspace root explicitly — avoids Next.js inferring the wrong
  // root when a stray lockfile exists elsewhere on the machine (e.g. in the
  // user's home directory outside this repo).
  turbopack: {
    root: path.join(__dirname),
  },
};

export default nextConfig;
