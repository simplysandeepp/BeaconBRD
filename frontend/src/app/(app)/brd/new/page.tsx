"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useSessionStore } from "@/store/useSessionStore";

export default function NewBRDPage() {
    const router = useRouter();
    const params = useSearchParams();
    const { activeSessionId } = useSessionStore();

    useEffect(() => {
        // Route legacy wizard users into the real, functional flow.
        if (activeSessionId) {
            router.replace("/ingestion");
        }
    }, [activeSessionId, router]);

    const name = params.get("name") ?? "New BRD Session";

    return (
        <div className="min-h-screen flex items-center justify-center p-6">
            <div className="max-w-xl w-full rounded-2xl border border-white/10 bg-zinc-900/60 p-8 text-center space-y-4">
                <h1 className="text-2xl font-semibold text-zinc-100">{name}</h1>
                <p className="text-sm text-zinc-400">
                    The legacy wizard has been replaced with the real flow.
                    Use ingestion for live source sync, then generate BRD from the BRD tab.
                </p>
                <div className="flex items-center justify-center gap-3 pt-2">
                    <Link href="/ingestion">
                        <button className="btn-primary text-sm py-2 px-4">
                            Go to Ingestion
                            <ArrowRight size={13} className="inline ml-2" />
                        </button>
                    </Link>
                    <Link href="/brd">
                        <button className="btn-secondary text-sm py-2 px-4">Go to BRD</button>
                    </Link>
                </div>
            </div>
        </div>
    );
}
