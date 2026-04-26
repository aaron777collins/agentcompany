import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Deep navy/slate base — primary surface colors
        surface: {
          DEFAULT: '#0f1117',
          1: '#151821',
          2: '#1a1d28',
          3: '#1f2333',
          4: '#252840',
          border: '#2a2f45',
          hover: '#2e3450',
        },
        // Brand accent — used for highlights, active states
        accent: {
          DEFAULT: '#6366f1',
          hover: '#818cf8',
          muted: '#4338ca',
          subtle: '#1e1b4b',
        },
        // Agent status colors — must be visually distinct at a glance
        status: {
          active: '#22c55e',
          idle: '#eab308',
          error: '#ef4444',
          stopped: '#6b7280',
          pending: '#3b82f6',
        },
        // Semantic text hierarchy
        text: {
          primary: '#f1f5f9',
          secondary: '#94a3b8',
          muted: '#475569',
          disabled: '#334155',
        },
      },
      fontFamily: {
        // Inter as primary; system stack fallback ensures zero CLS on slow loads
        sans: [
          'Inter',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI"',
          'Roboto',
          'sans-serif',
        ],
        mono: [
          '"JetBrains Mono"',
          '"Fira Code"',
          'ui-monospace',
          'SFMono-Regular',
          'Menlo',
          'monospace',
        ],
      },
      animation: {
        'fade-in': 'fadeIn 0.2s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'slide-down': 'slideDown 0.2s ease-out',
        'enter': 'enter 0.25s ease-out',
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'spin-slow': 'spin 2s linear infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideDown: {
          '0%': { opacity: '0', transform: 'translateY(-8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        enter: {
          '0%': { opacity: '0', transform: 'translateX(-6px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
      },
      boxShadow: {
        // Layered shadows create depth without heavy borders
        card: '0 1px 3px rgba(0,0,0,0.4), 0 1px 2px rgba(0,0,0,0.3)',
        elevated: '0 4px 16px rgba(0,0,0,0.5), 0 2px 6px rgba(0,0,0,0.4)',
        modal: '0 20px 60px rgba(0,0,0,0.7), 0 8px 24px rgba(0,0,0,0.5)',
        glow: '0 0 20px rgba(99,102,241,0.3)',
      },
      borderRadius: {
        DEFAULT: '0.5rem',
      },
    },
  },
  plugins: [],
};

export default config;
