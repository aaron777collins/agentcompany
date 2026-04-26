'use client';

/**
 * useTheme — dark/light mode toggle with localStorage persistence.
 *
 * We manage the theme by toggling the `dark` class on <html>. Tailwind's
 * `darkMode: 'class'` configuration reads this class to apply dark: variants.
 *
 * Default is dark mode (matches the design system). The preference is written
 * to localStorage under the key `ac_theme` so it survives page refreshes.
 */

import { useEffect, useState, useCallback } from 'react';

type Theme = 'dark' | 'light';

const STORAGE_KEY = 'ac_theme';

function getInitialTheme(): Theme {
  if (typeof window === 'undefined') return 'dark';
  const stored = localStorage.getItem(STORAGE_KEY) as Theme | null;
  return stored ?? 'dark';
}

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === 'dark') {
    root.classList.add('dark');
    root.setAttribute('style', 'color-scheme: dark');
  } else {
    root.classList.remove('dark');
    root.setAttribute('style', 'color-scheme: light');
  }
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>('dark');

  // Hydrate from localStorage after mount to avoid SSR mismatch
  useEffect(() => {
    const initial = getInitialTheme();
    setThemeState(initial);
    applyTheme(initial);
  }, []);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    applyTheme(next);
    localStorage.setItem(STORAGE_KEY, next);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(theme === 'dark' ? 'light' : 'dark');
  }, [theme, setTheme]);

  return { theme, toggleTheme };
}
