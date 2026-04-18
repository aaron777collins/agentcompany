/**
 * Lightweight Keycloak OIDC integration using the Authorization Code + PKCE flow.
 *
 * Why PKCE and not client_secret? The web UI is a public client — there is no
 * safe place to store a secret in the browser. PKCE binds the authorization
 * code to the originating browser tab without needing a shared secret.
 *
 * Why not keycloak-js? The official library adds ~50 KB and pulls in legacy
 * implicit-flow logic we don't need. A targeted fetch-based implementation
 * keeps the bundle lean and makes the auth contract explicit.
 *
 * Storage: tokens are kept in localStorage so they survive page refreshes.
 * Production deployments should consider httpOnly cookies via a BFF instead,
 * but that requires server-side infrastructure outside MVP scope.
 */

// ---------------------------------------------------------------------------
// Configuration — sourced from env vars at build time
// ---------------------------------------------------------------------------

const KEYCLOAK_URL = process.env.NEXT_PUBLIC_KEYCLOAK_URL ?? '';
const REALM = process.env.NEXT_PUBLIC_KEYCLOAK_REALM ?? 'agentcompany';
const CLIENT_ID = process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT_ID ?? 'web-ui';

/** True when Keycloak env vars are provided — false in bare dev environments. */
export const AUTH_ENABLED =
  typeof window !== 'undefined' &&
  KEYCLOAK_URL.length > 0 &&
  REALM.length > 0 &&
  CLIENT_ID.length > 0;

const BASE_OIDC = `${KEYCLOAK_URL}/realms/${REALM}/protocol/openid-connect`;

// ---------------------------------------------------------------------------
// Storage keys
// ---------------------------------------------------------------------------

const STORAGE_KEY = {
  ACCESS_TOKEN: 'ac_access_token',
  REFRESH_TOKEN: 'ac_refresh_token',
  ID_TOKEN: 'ac_id_token',
  EXPIRES_AT: 'ac_expires_at',
  CODE_VERIFIER: 'ac_pkce_verifier',
  AUTH_STATE: 'ac_auth_state',
} as const;

// ---------------------------------------------------------------------------
// PKCE helpers
// ---------------------------------------------------------------------------

/** Generates a cryptographically random string for use as a PKCE code verifier. */
function generateCodeVerifier(): string {
  const array = new Uint8Array(64);
  crypto.getRandomValues(array);
  return base64UrlEncode(array);
}

/**
 * Derives the PKCE code challenge from the verifier using S256 method.
 * S256 is mandatory for all new public clients per RFC 7636 §4.2.
 */
async function generateCodeChallenge(verifier: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(verifier);
  const digest = await crypto.subtle.digest('SHA-256', data);
  return base64UrlEncode(new Uint8Array(digest));
}

function base64UrlEncode(bytes: Uint8Array): string {
  let str = '';
  for (const byte of bytes) {
    str += String.fromCharCode(byte);
  }
  return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

// ---------------------------------------------------------------------------
// Token storage (synchronous wrappers so callers stay simple)
// ---------------------------------------------------------------------------

interface StoredTokens {
  accessToken: string;
  refreshToken: string;
  idToken: string;
  expiresAt: number; // unix milliseconds
}

function saveTokens(tokens: StoredTokens): void {
  localStorage.setItem(STORAGE_KEY.ACCESS_TOKEN, tokens.accessToken);
  localStorage.setItem(STORAGE_KEY.REFRESH_TOKEN, tokens.refreshToken);
  localStorage.setItem(STORAGE_KEY.ID_TOKEN, tokens.idToken);
  localStorage.setItem(STORAGE_KEY.EXPIRES_AT, String(tokens.expiresAt));
}

function clearTokens(): void {
  Object.values(STORAGE_KEY).forEach((key) => localStorage.removeItem(key));
}

function loadTokens(): StoredTokens | null {
  const accessToken = localStorage.getItem(STORAGE_KEY.ACCESS_TOKEN);
  const refreshToken = localStorage.getItem(STORAGE_KEY.REFRESH_TOKEN);
  const idToken = localStorage.getItem(STORAGE_KEY.ID_TOKEN);
  const expiresAt = localStorage.getItem(STORAGE_KEY.EXPIRES_AT);
  if (!accessToken || !refreshToken || !idToken || !expiresAt) return null;
  return {
    accessToken,
    refreshToken,
    idToken,
    expiresAt: parseInt(expiresAt, 10),
  };
}

// ---------------------------------------------------------------------------
// Token refresh
// ---------------------------------------------------------------------------

/** In-flight refresh promise — prevents parallel refresh races. */
let refreshPromise: Promise<string> | null = null;

async function exchangeRefreshToken(refreshToken: string): Promise<StoredTokens> {
  const body = new URLSearchParams({
    grant_type: 'refresh_token',
    client_id: CLIENT_ID,
    refresh_token: refreshToken,
  });

  const res = await fetch(`${BASE_OIDC}/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Token refresh failed (${res.status}): ${text}`);
  }

  const json = await res.json();
  return tokensFromResponse(json);
}

function tokensFromResponse(json: Record<string, unknown>): StoredTokens {
  const expiresIn = (json.expires_in as number) ?? 300;
  return {
    accessToken: json.access_token as string,
    refreshToken: json.refresh_token as string,
    idToken: (json.id_token as string) ?? '',
    // Subtract 30 s buffer so we refresh before the server rejects the token
    expiresAt: Date.now() + (expiresIn - 30) * 1000,
  };
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Returns the current access token, refreshing it first if it is within 30 s
 * of expiry. Returns null when auth is disabled or not yet authenticated.
 */
export async function getToken(): Promise<string | null> {
  if (!AUTH_ENABLED) return null;

  const stored = loadTokens();
  if (!stored) return null;

  // Token still valid — return it directly
  if (Date.now() < stored.expiresAt) return stored.accessToken;

  // Token expired or close to expiry — refresh exactly once even under concurrency
  if (!refreshPromise) {
    refreshPromise = exchangeRefreshToken(stored.refreshToken)
      .then((fresh) => {
        saveTokens(fresh);
        return fresh.accessToken;
      })
      .catch((err) => {
        // Refresh failed (e.g., refresh token itself expired) — force re-login
        clearTokens();
        throw err;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }

  return refreshPromise;
}

/** Returns true when a valid (or refreshable) session exists. */
export function isAuthenticated(): boolean {
  if (!AUTH_ENABLED) return true; // dev mode — treat as always authenticated
  return loadTokens() !== null;
}

/**
 * Initiates the PKCE authorization code flow.
 * Stores the code verifier and a random state value in localStorage before
 * redirecting so `handleCallback` can verify them on return.
 */
export async function login(): Promise<void> {
  if (!AUTH_ENABLED) return;

  const verifier = generateCodeVerifier();
  const challenge = await generateCodeChallenge(verifier);
  const state = base64UrlEncode(crypto.getRandomValues(new Uint8Array(16)));

  localStorage.setItem(STORAGE_KEY.CODE_VERIFIER, verifier);
  localStorage.setItem(STORAGE_KEY.AUTH_STATE, state);

  const redirectUri = `${window.location.origin}/auth/callback`;

  const params = new URLSearchParams({
    response_type: 'code',
    client_id: CLIENT_ID,
    redirect_uri: redirectUri,
    scope: 'openid profile email',
    state,
    code_challenge: challenge,
    code_challenge_method: 'S256',
  });

  window.location.href = `${BASE_OIDC}/auth?${params.toString()}`;
}

/**
 * Handles the OAuth callback after Keycloak redirects back.
 * Must be called from the `/auth/callback` route.
 *
 * Returns true on success, throws on state mismatch or token exchange failure.
 */
export async function handleCallback(searchParams: URLSearchParams): Promise<void> {
  const code = searchParams.get('code');
  const returnedState = searchParams.get('state');
  const error = searchParams.get('error');

  if (error) {
    throw new Error(`Authorization error: ${error} — ${searchParams.get('error_description') ?? ''}`);
  }

  if (!code) {
    throw new Error('Missing authorization code in callback URL');
  }

  const storedState = localStorage.getItem(STORAGE_KEY.AUTH_STATE);
  if (!storedState || returnedState !== storedState) {
    throw new Error('OAuth state mismatch — possible CSRF attack, aborting');
  }

  const verifier = localStorage.getItem(STORAGE_KEY.CODE_VERIFIER);
  if (!verifier) {
    throw new Error('Missing PKCE code verifier — cannot complete token exchange');
  }

  const redirectUri = `${window.location.origin}/auth/callback`;

  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    client_id: CLIENT_ID,
    code,
    redirect_uri: redirectUri,
    code_verifier: verifier,
  });

  const res = await fetch(`${BASE_OIDC}/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Token exchange failed (${res.status}): ${text}`);
  }

  const json = await res.json();
  saveTokens(tokensFromResponse(json));

  // Clean up PKCE state so a replay attack cannot reuse it
  localStorage.removeItem(STORAGE_KEY.CODE_VERIFIER);
  localStorage.removeItem(STORAGE_KEY.AUTH_STATE);
}

/**
 * Clears local tokens and redirects to the Keycloak end-session endpoint.
 * The user is then redirected back to the app root after logout.
 */
export function logout(): void {
  if (!AUTH_ENABLED) return;

  const idToken = localStorage.getItem(STORAGE_KEY.ID_TOKEN) ?? '';
  clearTokens();

  const redirectUri = encodeURIComponent(window.location.origin);
  const params = new URLSearchParams({
    client_id: CLIENT_ID,
    post_logout_redirect_uri: window.location.origin,
    ...(idToken ? { id_token_hint: idToken } : {}),
  });

  window.location.href = `${BASE_OIDC}/logout?${params.toString()}`;
}
