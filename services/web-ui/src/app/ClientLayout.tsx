'use client';

/**
 * ClientLayout separates the interactive parts of the root layout (Sidebar,
 * CommandPalette, keyboard shortcuts) from the server-renderable metadata in
 * layout.tsx. This is the minimal 'use client' boundary.
 *
 * Auth strategy: AuthGuard wraps the app shell so every page is protected.
 * The /auth/callback route is rendered by layout.tsx with isCallback=true,
 * bypassing the guard — it is the endpoint that completes authentication and
 * must be reachable before a session exists.
 */

import React, { useState, useCallback, useEffect } from 'react';
import { usePathname } from 'next/navigation';
import Sidebar from '@/components/layout/Sidebar';
import CommandPalette from '@/components/layout/CommandPalette';
import AuthGuard from '@/components/layout/AuthGuard';

export default function ClientLayout({ children }: { children: React.ReactNode }) {
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const pathname = usePathname();

  // Global Cmd+K / Ctrl+K handler
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      setCommandPaletteOpen((prev) => !prev);
    }
  }, []);

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  // The callback page completes authentication — it must not be guarded.
  const isAuthCallback = pathname === '/auth/callback';

  if (isAuthCallback) {
    // Render without the app shell so the callback page has a clean canvas
    return <>{children}</>;
  }

  return (
    <AuthGuard>
      <div className="flex h-screen overflow-hidden bg-surface">
        <Sidebar />

        {/* Main content area */}
        <main className="flex-1 flex flex-col overflow-hidden ml-60">
          <div className="flex-1 overflow-y-auto">
            {children}
          </div>
        </main>

        <CommandPalette
          open={commandPaletteOpen}
          onClose={() => setCommandPaletteOpen(false)}
        />
      </div>
    </AuthGuard>
  );
}
