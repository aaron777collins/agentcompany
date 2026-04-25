import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

/**
 * Next.js Edge Middleware — runs before every matched request.
 *
 * Responsibilities:
 *  1. Attach security headers to all responses. These are a defence-in-depth
 *     layer; they do not replace server-side auth checks.
 *  2. Leave /_next/, /api/, and /auth/callback untouched so the framework's
 *     own routing and the OIDC callback flow work correctly.
 *
 * Why middleware for headers and not only next.config.js headers()? The
 * config-level headers() hook runs at build time and cannot branch on runtime
 * request properties. Middleware gives us that flexibility without a custom
 * server, and it runs in the lightweight Edge Runtime (no cold-start penalty).
 */

// Paths that must not be blocked or redirected by this middleware
const BYPASS_PREFIXES = ['/_next/', '/api/', '/auth/callback'];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Pass through framework internals and the auth endpoint unchanged
  if (BYPASS_PREFIXES.some((prefix) => pathname.startsWith(prefix))) {
    return NextResponse.next();
  }

  const response = NextResponse.next();

  // Prevent browsers from MIME-sniffing the response away from the declared
  // Content-Type — mitigates content-injection via uploaded assets
  response.headers.set('X-Content-Type-Options', 'nosniff');

  // Deny embedding in frames entirely — eliminates clickjacking surface
  response.headers.set('X-Frame-Options', 'DENY');

  // Legacy XSS filter — modern browsers ignore it but older ones respect it
  response.headers.set('X-XSS-Protection', '1; mode=block');

  // Only send the full origin on same-origin requests; send just the origin
  // (no path) on cross-origin navigations — avoids leaking internal URLs
  response.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');

  // Opt out of browser features not used by the app; reduces attack surface
  // if a dependency is ever compromised via XSS
  response.headers.set(
    'Permissions-Policy',
    'camera=(), microphone=(), geolocation=()',
  );

  return response;
}

export const config = {
  // Match every route except Next.js static file serving (_next/static, _next/image)
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
};
