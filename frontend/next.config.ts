import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: 'standalone',

  // Expose env vars to browser-side code.
  // `??` not `||` for the port: an explicitly empty value means "same origin, let
  // nginx proxy /api" and must survive. `||` would treat '' as unset and bake in
  // :8000, which is bound to localhost only in production — every call would fail.
  // Unset still falls back to 8000 for local dev against `runserver`.
  env: {
    NEXT_PUBLIC_API_PROTOCOL: process.env.NEXT_PUBLIC_API_PROTOCOL || 'http',
    NEXT_PUBLIC_API_PORT: process.env.NEXT_PUBLIC_API_PORT ?? '8000',
    NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE ?? '',
  },

  // Optimize images
  images: {
    formats: ['image/avif', 'image/webp'],
    minimumCacheTTL: 60,
  },

  // Production optimizations
  poweredByHeader: false,
  compress: true,

  // Headers for security
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
        ],
      },
    ];
  },
};

export default nextConfig;
