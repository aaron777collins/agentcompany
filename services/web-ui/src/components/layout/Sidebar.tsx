'use client';

/**
 * Sidebar — responsive navigation rail.
 *
 * Breakpoints:
 *   - Mobile (<768px):  hidden by default; opens as a full-height drawer via
 *     `mobileOpen` state toggled by the hamburger button in Header.
 *   - Tablet (768-1199px): visible as an icon-only rail (w-16); labels hidden.
 *   - Desktop (1200px+): full sidebar with icons + labels (w-60).
 *
 * The `ml-60` on the main content area in ClientLayout only activates at md+,
 * matching the point at which the sidebar becomes visible.
 */

import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cx } from '@/lib/utils';

interface NavItem {
  href: string;
  label: string;
  icon: React.ReactNode;
  badge?: number;
}

const navItems: NavItem[] = [
  {
    href: '/',
    label: 'Dashboard',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
          d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
      </svg>
    ),
  },
  {
    href: '/org-chart',
    label: 'Org Chart',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
          d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
  },
  {
    href: '/agents',
    label: 'Agents',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
          d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17H3a2 2 0 01-2-2V5a2 2 0 012-2h16a2 2 0 012 2v10a2 2 0 01-2 2h-2" />
      </svg>
    ),
  },
  {
    href: '/tasks',
    label: 'Task Board',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
          d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
      </svg>
    ),
  },
  {
    href: '/companies',
    label: 'Companies',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
          d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
      </svg>
    ),
  },
  {
    href: '/search',
    label: 'Search',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
          d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
      </svg>
    ),
  },
];

const bottomNavItems: NavItem[] = [
  {
    href: '/settings',
    label: 'Settings',
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
          d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
  },
];

interface SidebarNavItemProps {
  item: NavItem;
  active: boolean;
  /** When true only renders the icon (tablet rail mode) */
  collapsed: boolean;
  onClick?: () => void;
}

const SidebarNavItem: React.FC<SidebarNavItemProps> = ({ item, active, collapsed, onClick }) => (
  <Link
    href={item.href}
    onClick={onClick}
    title={collapsed ? item.label : undefined}
    className={cx(
      'flex items-center rounded-lg text-sm font-medium transition-all duration-150',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent',
      collapsed ? 'justify-center p-2.5' : 'gap-3 px-3 py-2',
      active
        ? 'bg-accent/10 text-accent border border-accent/20'
        : 'text-text-secondary hover:text-text-primary hover:bg-surface-3 border border-transparent',
    )}
  >
    <span className={cx('shrink-0', active ? 'text-accent' : 'text-text-muted')}>
      {item.icon}
    </span>
    {!collapsed && <span>{item.label}</span>}
    {!collapsed && item.badge !== undefined && item.badge > 0 && (
      <span className="ml-auto flex h-5 min-w-5 items-center justify-center rounded-full bg-accent text-white text-xs font-semibold px-1">
        {item.badge > 99 ? '99+' : item.badge}
      </span>
    )}
  </Link>
);

interface SidebarProps {
  onCommandPaletteOpen?: () => void;
  theme?: 'dark' | 'light';
  onToggleTheme?: () => void;
}

const Sidebar: React.FC<SidebarProps> = ({ onCommandPaletteOpen, theme = 'dark', onToggleTheme }) => {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  const isActive = (href: string) =>
    href === '/' ? pathname === '/' : pathname.startsWith(href);

  const closeMobile = () => setMobileOpen(false);

  // Shared nav content — rendered in both mobile drawer and desktop sidebar
  function NavContent({ collapsed }: { collapsed: boolean }) {
    return (
      <>
        {/* Logo / brand */}
        <div className={cx(
          'flex items-center h-14 border-b border-surface-border shrink-0',
          collapsed ? 'justify-center px-2' : 'gap-2.5 px-4',
        )}>
          <div className="w-7 h-7 rounded-lg bg-accent flex items-center justify-center shadow-glow shrink-0">
            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5}
                d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          {!collapsed && (
            <span className="font-bold text-text-primary text-sm tracking-tight">AgentCompany</span>
          )}
        </div>

        {/* Main navigation */}
        <nav className={cx('flex-1 overflow-y-auto py-4 space-y-0.5', collapsed ? 'px-2' : 'px-3')}>
          {navItems.map((item) => (
            <SidebarNavItem
              key={item.href}
              item={item}
              active={isActive(item.href)}
              collapsed={collapsed}
              onClick={closeMobile}
            />
          ))}
        </nav>

        {/* Bottom section */}
        <div className={cx(
          'pb-4 border-t border-surface-border pt-3 space-y-0.5',
          collapsed ? 'px-2' : 'px-3',
        )}>
          {bottomNavItems.map((item) => (
            <SidebarNavItem
              key={item.href}
              item={item}
              active={isActive(item.href)}
              collapsed={collapsed}
              onClick={closeMobile}
            />
          ))}

          {/* Theme toggle */}
          {onToggleTheme && (
            <button
              onClick={onToggleTheme}
              title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
              className={cx(
                'w-full flex items-center rounded-lg text-sm font-medium transition-all duration-150',
                'text-text-secondary hover:text-text-primary hover:bg-surface-3 border border-transparent',
                collapsed ? 'justify-center p-2.5' : 'gap-3 px-3 py-2',
              )}
            >
              <span className="shrink-0 text-text-muted">
                {theme === 'dark' ? (
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
                      d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                  </svg>
                ) : (
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
                      d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                  </svg>
                )}
              </span>
              {!collapsed && (
                <span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>
              )}
            </button>
          )}

          {/* Cmd+K shortcut hint */}
          {onCommandPaletteOpen && !collapsed && (
            <button
              onClick={onCommandPaletteOpen}
              className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all text-text-secondary hover:text-text-primary hover:bg-surface-3 border border-transparent"
            >
              <span className="shrink-0 text-text-muted">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
                    d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </span>
              <span className="flex-1 text-left">Search</span>
              <kbd className="text-xs text-text-disabled border border-surface-border rounded px-1 py-0.5 font-mono">
                ⌘K
              </kbd>
            </button>
          )}
        </div>
      </>
    );
  }

  return (
    <>
      {/* Mobile hamburger button — visible only on small screens */}
      <button
        onClick={() => setMobileOpen(true)}
        className="md:hidden fixed top-3 left-3 z-40 p-2 rounded-lg bg-surface-1 border border-surface-border text-text-secondary hover:text-text-primary transition-colors"
        aria-label="Open navigation"
      >
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      {/* Mobile drawer overlay */}
      {mobileOpen && (
        <div
          className="md:hidden fixed inset-0 z-50 bg-black/60 backdrop-blur-sm animate-fade-in"
          onClick={closeMobile}
          aria-hidden="true"
        />
      )}

      {/* Mobile drawer */}
      <aside
        className={cx(
          'fixed left-0 top-0 h-screen flex flex-col border-r border-surface-border bg-surface-1 z-50',
          'w-60 transition-transform duration-300',
          'md:hidden',
          mobileOpen ? 'translate-x-0' : '-translate-x-full',
        )}
        aria-label="Navigation"
      >
        {/* Mobile close button */}
        <button
          onClick={closeMobile}
          className="absolute top-3 right-3 p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-surface-3 transition-colors"
          aria-label="Close navigation"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
        <NavContent collapsed={false} />
      </aside>

      {/* Tablet: icon-only rail (md screens) — hidden on lg+ */}
      <aside
        className="hidden md:flex lg:hidden fixed left-0 top-0 h-screen w-16 flex-col border-r border-surface-border bg-surface-1 z-30"
        aria-label="Navigation"
      >
        <NavContent collapsed={true} />
      </aside>

      {/* Desktop: full sidebar (lg+ screens) */}
      <aside
        className="hidden lg:flex fixed left-0 top-0 h-screen w-60 flex-col border-r border-surface-border bg-surface-1 z-30"
        aria-label="Navigation"
      >
        <NavContent collapsed={false} />
      </aside>
    </>
  );
};

export default Sidebar;
