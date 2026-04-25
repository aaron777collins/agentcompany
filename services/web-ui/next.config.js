/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',

  // Allow images from the API server for agent avatars and company logos
  images: {
    remotePatterns: [
      {
        protocol: 'http',
        hostname: 'localhost',
        port: '8000',
        pathname: '/**',
      },
    ],
  },

  /**
   * Forward /api/* to the backend.
   *
   * Security note: `destination` is built from an env var that is only set
   * at server start — it is never exposed to the browser. The rewrite strips
   * the internal hostname from the response path so clients see only /api/*.
   *
   * NEXT_PUBLIC_API_URL must NOT be set to a user-supplied value in production
   * deployments; it should come from infrastructure secrets.
   */
  async rewrites() {
    const apiBase = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api';
    return [
      {
        source: '/api/:path*',
        destination: `${apiBase}/:path*`,
      },
    ];
  },

  /**
   * Security headers applied at the CDN/infrastructure level.
   *
   * These complement the Edge Middleware headers (src/middleware.ts). Having
   * them in both places ensures headers are present even if middleware is
   * bypassed by a direct origin hit or a misconfigured CDN.
   */
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'X-XSS-Protection', value: '1; mode=block' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          {
            key: 'Permissions-Policy',
            value: 'camera=(), microphone=(), geolocation=()',
          },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
