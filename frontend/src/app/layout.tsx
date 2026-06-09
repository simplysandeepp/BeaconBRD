import type { Metadata } from 'next';
import { Inter, JetBrains_Mono } from 'next/font/google';
import '@/styles/globals.css';

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
    icons: {
        icon: 'https://framerusercontent.com/images/ubO6hprNRTUPSD1LOKrAqhScc.png',
    },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
    return (
        <html lang="en" className="dark">
            <head>
                {/*
                 * iframe-breakout script:
                 * If the app is running inside an iframe AND is NOT on the
                 * landing page (/), force the top-level window to navigate
                 * to this URL.  This ensures all auth pages (login, register,
                 * profile, dashboard, etc.) always render at the top level,
                 * never embedded inside the Framer iframe.
                 *
                 * The landing page (/) is SUPPOSED to be in an iframe, so
                 * we skip breakout for that path.
                 */}
                <script
                    dangerouslySetInnerHTML={{
                        __html: `
                            (function() {
                                try {
                                    if (window.self !== window.top && window.location.pathname !== '/') {
                                        window.top.location.href = window.location.href;
                                    }
                                } catch(e) {
                                    // Cross-origin restriction — ignore
                                }
                            })();
                        `,
                    }}
                />
            </head>
            <body className={`${inter.variable} ${jetbrainsMono.variable} font-sans antialiased`}>
                {children}
            </body>
        </html>
    );
}
