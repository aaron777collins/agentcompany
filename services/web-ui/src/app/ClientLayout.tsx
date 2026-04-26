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

import React, { useState, useCallback } from 'react';
import { usePathname } from 'next/navigation';
import Sidebar from '@/components/layout/Sidebar';
import CommandPalette from '@/components/layout/CommandPalette';
import KeyboardShortcuts from '@/components/layout/KeyboardShortcuts';
import AuthGuard from '@/components/layout/AuthGuard';
import { ToastProvider } from '@/components/ui/Toast';
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts';
import { useTheme } from '@/hooks/useTheme';

// Inner component has access to router (needed by useKeyboardShortcuts)
function AppShell({ children }: { children: React.ReactNode }) {
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const { theme, toggleTheme } = useTheme();

  const openCommandPalette = useCallback(() => setCommandPaletteOpen(true), []);
  const openShortcutsHelp = useCallback(() => setShortcutsOpen(true), []);

  useKeyboardShortcuts({
    onOpenCommandPalette: openCommandPalette,
    onOpenShortcutsHelp: openShortcutsHelp,
  });

  return (
    <div className="flex h-screen overflow-hidden bg-surface">
      <Sidebar
        onCommandPaletteOpen={openCommandPalette}
        theme={theme}
        onToggleTheme={toggleTheme}
      />

      {/* Main content area — offset by icon rail on md, full sidebar on lg */}
      <main className="flex-1 flex flex-col overflow-hidden md:ml-16 lg:ml-60">
        <div className="flex-1 overflow-y-auto">
          {children}
        </div>
      </main>

      <CommandPalette
        open={commandPaletteOpen}
        onClose={() => setCommandPaletteOpen(false)}
      />

      <KeyboardShortcuts
        open={shortcutsOpen}
        onClose={() => setShortcutsOpen(false)}
      />
    </div>
  );
}

export default function ClientLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isAuthCallback = pathname === '/auth/callback';

  if (isAuthCallback) {
    return (
      <ToastProvider>
        {children}
      </ToastProvider>
    );
  }

  return (
    <ToastProvider>
      <AuthGuard>
        <AppShell>{children}</AppShell>
      </AuthGuard>
    </ToastProvider>
  );
}
