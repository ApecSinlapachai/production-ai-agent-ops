import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    const target = (
      process.env.API_PROXY_TARGET ||
      process.env.NEXT_PUBLIC_API_BASE_URL ||
      "http://localhost:8000"
    ).replace(/\/+$/, "");

    return [
      {
        source: "/backend/:path*",
        destination: `${target}/:path*`,
      },
    ];
  },
};

export default nextConfig;
