'use client';

/**
 * ClientLayout separates the interactive parts of the root layout (Sidebar,
 * CommandPalette, keyboard shortcuts) from the server-renderable metadata in
 * layout.tsx. This is the minimal 'use client' boundary.
 */

import React, { useState, useCallback, useEffect } from 'react';
import Sidebar from '@/components/layout/Sidebar';
import CommandPalette from '@/components/layout/CommandPalette';

export default function ClientLayout({ children }: { children: React.ReactNode }) {
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);

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

  return (
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
  );
}
