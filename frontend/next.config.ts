import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  reactCompiler: true,
  // Next blocks dev resources (HMR, /_next/*) for origins other than localhost.
  // Without this, opening the app over the LAN address loads a half-dead page.
  allowedDevOrigins: ["localhost", "127.0.0.1", "192.168.1.36"],
};

export default nextConfig;
