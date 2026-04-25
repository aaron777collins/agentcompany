'use client';

/**
 * Auth callback page — receives the Keycloak redirect after login.
 *
 * Why a dedicated page instead of an API route? handleCallback() calls
 * localStorage and crypto.subtle, both of which are browser-only APIs that
 * cannot run inside a Next.js Route Handler (Node.js environment).
 *
 * Why the Suspense wrapper? useSearchParams() triggers Suspense in the
 * App Router; wrapping CallbackInner keeps the outer page statically
 * renderable while the inner reads the URL parameters on the client.
 */

import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { handleCallback } from '@/lib/auth';
import Spinner from '@/components/ui/Spinner';
import Button from '@/components/ui/Button';

// ---------------------------------------------------------------------------
// Inner component — runs only in the browser where searchParams are available
// ---------------------------------------------------------------------------

function CallbackInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function processCallback() {
      try {
        await handleCallback(searchParams);
        // Replace (not push) so the user cannot land back on this URL via Back
        router.replace('/');
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Authentication failed');
      }
    }
    processCallback();
    // searchParams is derived from the immutable URL on first render — runs once
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-surface gap-6 px-4">
        <div className="w-full max-w-md rounded-xl border border-status-error/30 bg-status-error/5 p-8 text-center">
          {/* Error icon */}
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-status-error/10">
            <svg
              className="h-6 w-6 text-status-error"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"
              />
            </svg>
          </div>

          <h1 className="mb-2 text-lg font-semibold text-text-primary">Sign-in failed</h1>
          <p className="mb-6 text-sm text-text-muted break-words">{error}</p>

          <Button
            variant="primary"
            onClick={() => {
              // Navigate to root — AuthGuard will trigger a fresh login if needed
              window.location.href = '/';
            }}
          >
            Return to home
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-surface gap-4">
      <Spinner size="lg" />
      <p className="text-sm text-text-muted animate-pulse">Signing in…</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page export — Suspense boundary required by Next.js App Router
// ---------------------------------------------------------------------------

const SigningInFallback = () => (
  <div className="flex flex-col items-center justify-center min-h-screen bg-surface gap-4">
    <Spinner size="lg" />
    <p className="text-sm text-text-muted animate-pulse">Signing in…</p>
  </div>
);

export default function AuthCallbackPage() {
  return (
    <Suspense fallback={<SigningInFallback />}>
      <CallbackInner />
    </Suspense>
  );
}
