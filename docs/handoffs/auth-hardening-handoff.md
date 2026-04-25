# Auth Hardening Handoff

Date: 2026-04-18
Author: Staff Engineer (Claude Sonnet 4.6)

---

## What was done

Four changes were made to `services/web-ui/` to close the auth loop and harden security posture.

---

### 1. Auth Callback Page

**File:** `src/app/auth/callback/page.tsx`

The Keycloak PKCE flow redirects the browser to `/auth/callback?code=…&state=…` after login. Previously that URL returned a 404. The new page:

- Calls `handleCallback(searchParams)` from `auth.ts`, which verifies the OAuth `state` parameter (CSRF protection) and exchanges the code for tokens via the PKCE `code_verifier`.
- On success: `router.replace('/')` — uses replace rather than push so the callback URL is not in browser history.
- On error: renders a full-page error card with the specific failure reason and a "Return to home" button.
- Wraps the inner component in a `Suspense` boundary because Next.js App Router requires it when `useSearchParams()` is used.

---

### 2. AuthGuard Component + ClientLayout Integration

**Files:** `src/components/layout/AuthGuard.tsx`, `src/app/ClientLayout.tsx`

`AuthGuard` is a client component that checks `isAuthenticated()` on mount:

- **Auth enabled, not authenticated:** calls `login()` to start the PKCE flow and shows "Redirecting to sign in…"
- **Auth enabled, authenticated:** renders children
- **Auth disabled** (`AUTH_ENABLED === false`, i.e., no Keycloak env vars): renders children immediately — developers can work without a running IdP

`ClientLayout` now detects `pathname === '/auth/callback'` and renders children without the AuthGuard or the Sidebar shell. This is the correct escape hatch — the callback page must be reachable before any session exists.

All other routes are wrapped in `<AuthGuard><div className="flex h-screen …">…</div></AuthGuard>`.

---

### 3. Security Headers

**Files:** `src/middleware.ts`, `next.config.js`

Headers are set in two places deliberately:

- **`src/middleware.ts`** (Edge Runtime): applied per-request, allowing future branching on request properties. Skips `/_next/`, `/api/`, and `/auth/callback` prefixes.
- **`next.config.js` `headers()`**: applied at the infrastructure level, ensuring headers are present even if a CDN bypasses middleware on a direct origin hit.

Headers applied:

| Header | Value | Why |
|--------|-------|-----|
| `X-Content-Type-Options` | `nosniff` | Prevents MIME-sniffing attacks on uploaded content |
| `X-Frame-Options` | `DENY` | Eliminates clickjacking surface |
| `X-XSS-Protection` | `1; mode=block` | Legacy filter for older browsers |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Avoids leaking internal URL paths cross-origin |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` | Reduces XSS-exploitable browser feature surface |

The API rewrite in `next.config.js` was also documented with a note that `NEXT_PUBLIC_API_URL` must come from infrastructure secrets in production, not user input.

---

### 4. Header Auth Controls

**File:** `src/components/layout/Header.tsx`

The `AuthControls` component was added to the right side of the header:

- Reads the stored access token via `getToken()` (handles silent refresh) and decodes the JWT payload client-side for display only — signature verification is the API server's job.
- Displays `name` → `given_name` → `preferred_username` → `email` → `'User'` in preference order from the token claims.
- Shows an avatar with initials (deterministic, no external image request).
- Logout button calls `logout()`, which clears localStorage tokens and redirects to the Keycloak end-session endpoint.
- When not authenticated and auth is enabled: shows a "Sign In" button that calls `login()`.
- When auth is disabled (dev mode): renders nothing.

---

## Known pre-existing issue

`src/lib/auth.ts` line 71 has a TypeScript error:

```
Type 'Uint8Array' can only be iterated through when using '--downlevelIteration'
flag or with a '--target' of 'es2015' or higher.
```

This is because `tsconfig.json` omits `"target"` (defaults to ES3). None of the files added in this session contribute new TypeScript errors. Fix: add `"target": "es2017"` (or higher) to `tsconfig.json`.

---

## Environment variables required for auth

| Variable | Example | Notes |
|----------|---------|-------|
| `NEXT_PUBLIC_KEYCLOAK_URL` | `https://auth.example.com` | Keycloak base URL, no trailing slash |
| `NEXT_PUBLIC_KEYCLOAK_REALM` | `agentcompany` | Realm name |
| `NEXT_PUBLIC_KEYCLOAK_CLIENT_ID` | `web-ui` | Public client ID (no secret) |

When these are absent, `AUTH_ENABLED` is `false` and all auth UI/guards are bypassed.

---

## What is not yet done

- **httpOnly cookie BFF**: The current implementation stores tokens in `localStorage`. This is called out in `auth.ts` as an MVP trade-off. A production hardening pass should add a thin BFF (Backend-for-Frontend) that issues httpOnly session cookies and holds tokens server-side.
- **Token expiry refresh on AuthGuard**: `AuthGuard` calls `isAuthenticated()` which only checks whether tokens exist in localStorage, not whether the access token is still valid. A follow-up should call `getToken()` and handle the case where the refresh token has also expired (force re-login).
- **CSP header**: A `Content-Security-Policy` header was intentionally omitted — it requires knowing all script/style/connect sources and will need input from the infrastructure team to avoid breaking legitimate loads.
