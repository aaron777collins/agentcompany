'use client';

/**
 * Application header — sticky bar at the top of every page.
 *
 * Auth controls are rendered on the right side:
 *  - Authenticated: avatar/name extracted from the JWT access token, plus a
 *    logout button. Parsing the token client-side is safe here because the UI
 *    only uses the claims for display; all real authorization is enforced by
 *    the API server, which verifies the signature.
 *  - Not authenticated (auth enabled): "Sign In" button.
 *  - Auth disabled (dev mode): no auth UI — avoids confusing devs without IdP.
 */

import React, { useEffect, useState } from 'react';
import { cx } from '@/lib/utils';
import Button from '@/components/ui/Button';
import { AUTH_ENABLED, isAuthenticated, login, logout, getToken } from '@/lib/auth';

// ---------------------------------------------------------------------------
// JWT claim types — only the subset we display
// ---------------------------------------------------------------------------

interface TokenClaims {
  name?: string;
  preferred_username?: string;
  email?: string;
  given_name?: string;
}

/**
 * Decodes the payload of a JWT without verifying the signature.
 * Signature verification is the API server's responsibility.
 */
function decodeTokenClaims(token: string): TokenClaims | null {
  try {
    const [, payloadB64] = token.split('.');
    // JWT base64url → standard base64 → JSON
    const padded = payloadB64.replace(/-/g, '+').replace(/_/g, '/');
    const json = atob(padded);
    return JSON.parse(json) as TokenClaims;
  } catch {
    // Malformed token — fail silently, UI degrades gracefully
    return null;
  }
}

function displayName(claims: TokenClaims): string {
  return (
    claims.name ??
    claims.given_name ??
    claims.preferred_username ??
    claims.email ??
    'User'
  );
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');
}

// ---------------------------------------------------------------------------
// Auth UI — isolated so the main Header stays readable
// ---------------------------------------------------------------------------

function AuthControls() {
  const [claims, setClaims] = useState<TokenClaims | null>(null);
  const [logoutLoading, setLogoutLoading] = useState(false);

  useEffect(() => {
    if (!AUTH_ENABLED || !isAuthenticated()) return;

    // getToken() handles refresh transparently; we only need it for the claims
    getToken().then((token) => {
      if (token) setClaims(decodeTokenClaims(token));
    });
  }, []);

  // Auth disabled — nothing to show in dev mode
  if (!AUTH_ENABLED) return null;

  if (!isAuthenticated()) {
    return (
      <Button
        variant="primary"
        size="sm"
        onClick={() => login()}
      >
        Sign In
      </Button>
    );
  }

  const name = claims ? displayName(claims) : '…';
  const userInitials = claims ? initials(displayName(claims)) : '?';

  function handleLogout() {
    setLogoutLoading(true);
    // logout() navigates away; loading state prevents double-clicks
    logout();
  }

  return (
    <div className="flex items-center gap-2">
      {/* Avatar + name */}
      <div className="flex items-center gap-2">
        <div
          className={cx(
            'flex h-7 w-7 shrink-0 items-center justify-center rounded-full',
            'bg-accent/20 text-accent text-xs font-semibold select-none',
          )}
          aria-hidden="true"
        >
          {userInitials}
        </div>
        <span className="hidden sm:block text-sm text-text-secondary max-w-[120px] truncate">
          {name}
        </span>
      </div>

      {/* Logout */}
      <Button
        variant="ghost"
        size="sm"
        loading={logoutLoading}
        onClick={handleLogout}
        title="Sign out"
        className="text-text-muted hover:text-text-primary"
      >
        <svg
          className="w-3.5 h-3.5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
          />
        </svg>
        <span className="sr-only">Sign out</span>
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Header
// ---------------------------------------------------------------------------

interface HeaderProps {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  onCommandPaletteOpen?: () => void;
}

const Header: React.FC<HeaderProps> = ({ title, subtitle, actions, onCommandPaletteOpen }) => (
  <header className="sticky top-0 z-20 flex items-center justify-between h-14 px-6 border-b border-surface-border bg-surface/80 backdrop-blur-md shrink-0">
    {/* Page title */}
    <div className="flex items-baseline gap-2">
      <h1 className="text-base font-semibold text-text-primary">{title}</h1>
      {subtitle && (
        <span className="text-sm text-text-muted hidden sm:block">{subtitle}</span>
      )}
    </div>

    {/* Right side actions */}
    <div className="flex items-center gap-2">
      {actions}

      {/* Cmd+K search shortcut hint */}
      <Button
        variant="ghost"
        size="sm"
        onClick={onCommandPaletteOpen}
        className="hidden md:flex gap-1.5 text-text-muted"
      >
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <span className="text-xs">Search</span>
        <kbd className={cx(
          'inline-flex items-center gap-0.5 rounded border border-surface-border',
          'px-1.5 py-0.5 text-xs font-mono text-text-disabled'
        )}>
          ⌘K
        </kbd>
      </Button>

      {/* Auth controls — sign in / user info + logout */}
      <div className="border-l border-surface-border pl-2 ml-1">
        <AuthControls />
      </div>
    </div>
  </header>
);

export default Header;
