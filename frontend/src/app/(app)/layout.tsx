'use client';

import { useEffect } from 'react';
import dynamic from 'next/dynamic';

const AuthProvider = dynamic(() => import('@/contexts/AuthContext').then(m => ({ default: m.AuthProvider })), {
    ssr: false,
    loading: () => (
        <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--bg-base)' }}>
            <div className="text-center">
                <div className="w-7 h-7 border-2 border-zinc-600 border-t-zinc-300 rounded-full animate-spin mx-auto mb-3" />
                <p className="text-zinc-600 text-sm">Loading...</p>
            </div>
        </div>
    ),
});

export default function AppLayout({ children }: { children: React.ReactNode }) {
    return <AuthProvider>{children}</AuthProvider>;
}
