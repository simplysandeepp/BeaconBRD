/* —— COMMENTED OUT (original) ——
   The original root layout with AuthProvider + fonts has been disabled
   so the static landing page at /public/landing.html serves as the main
   landing page. The AuthProvider is NOT wrapped globally anymore.

   To restore: uncomment the original code below and restore page.tsx.

import type { Metadata } from 'next';
import { Inter, JetBrains_Mono } from 'next/font/google';
import '@/styles/globals.css';
import { AuthProvider } from '@/contexts/AuthContext';

const inter = Inter({
    subsets: ['latin'],
    variable: '--font-inter',
    display: 'swap',
});

const jetbrainsMono = JetBrains_Mono({
    subsets: ['latin'],
    variable: '--font-mono',
    display: 'swap',
});

export const metadata: Metadata = {
    title: 'Beacon',
    description: 'AI-Powered Business Requirements Generator',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
    return (
        <html lang="en" className="dark">
            <body className={`${inter.variable} ${jetbrainsMono.variable} font-sans antialiased`}>
                <AuthProvider>{children}</AuthProvider>
            </body>
        </html>
    );
}
*/

// Minimal pass-through layout while static landing page is active
export default function RootLayout({ children }: { children: React.ReactNode }) {
    return <>{children}</>;
}
