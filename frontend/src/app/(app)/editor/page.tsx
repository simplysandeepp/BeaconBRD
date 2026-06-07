"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function EditorPage() {
    const router = useRouter();

    useEffect(() => {
        router.replace("/brd");
    }, [router]);

    return (
        <div className="p-8 text-sm text-zinc-400">
            Redirecting to BRD editor...
        </div>
    );
}
