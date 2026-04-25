'use client';

/**
 * AuthGuard — protects all app pages behind a Keycloak login.
 *
 * Why client-side rather than middleware? Tokens live in localStorage, which
 * is inaccessible to Next.js Middleware (runs in the Edge Runtime before the
 * browser). Middleware adds security headers (see middleware.ts); AuthGuard
 * handles the interactive redirect-to-login UX.
 *
 * When AUTH_ENABLED is false (no Keycloak env vars — local dev), the guard
 * renders children immediately so developers don't need a running IdP.
 */

import { useEffect, useState } from 'react';
import { AUTH_ENABLED, isAuthenticated, login } from '@/lib/auth';
import Spinner from '@/components/ui/Spinner';

interface AuthGuardProps {
  children: React.ReactNode;
}

export default function AuthGuard({ children }: AuthGuardProps) {
  // Three states: 'checking' | 'authenticated' | 'redirecting'
  const [authState, setAuthState] = useState<'checking' | 'authenticated' | 'redirecting'>(
    'checking',
  );

  useEffect(() => {
    // Auth is disabled in dev — skip the check entirely
    if (!AUTH_ENABLED) {
      setAuthState('authenticated');
      return;
    }

    if (isAuthenticated()) {
      setAuthState('authenticated');
    } else {
      // Mark as redirecting first so we don't flash the children
      setAuthState('redirecting');
      // login() is async (generates PKCE challenge) then immediately navigates
      login().catch((err) => {
        // If login itself fails (e.g., bad env config) surface it instead of
        // silently hanging on the loading screen
        console.error('AuthGuard: login() failed', err);
      });
    }
  }, []);

  if (authState === 'checking' || authState === 'redirecting') {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-surface gap-4">
        <Spinner size="lg" />
        <p className="text-sm text-text-muted animate-pulse">
          {authState === 'redirecting' ? 'Redirecting to sign in…' : 'Loading…'}
        </p>
      </div>
    );
  }

  return <>{children}</>;
}
