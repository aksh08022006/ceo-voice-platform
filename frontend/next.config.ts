import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Vercel's adapter packages the server itself; standalone is for self-hosted builds.
  output: process.env.VERCEL ? undefined : "standalone",
  env: { NEXT_PUBLIC_AUTH_ENABLED: String(Boolean(process.env.NEON_AUTH_BASE_URL || process.env.NEON_AUTH_COOKIE_SECRET)) },
  poweredByHeader: false,
  reactStrictMode: true,
};

export default nextConfig;
