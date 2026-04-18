import type { Metadata } from 'next';
import './globals.css';
import ClientLayout from './ClientLayout';

export const metadata: Metadata = {
  title: {
    default: 'AgentCompany',
    template: '%s | AgentCompany',
  },
  description: 'Build and run AI-powered companies with open-source tools',
  keywords: ['AI agents', 'agent orchestration', 'company automation'],
  // Disable indexing until the product is public
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body>
        <ClientLayout>{children}</ClientLayout>
      </body>
    </html>
  );
}
