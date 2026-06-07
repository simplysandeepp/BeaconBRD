
"use client";

import AgentOrchestrator from "@/components/workspace/AgentOrchestrator";
import { useSessionStore } from "@/store/useSessionStore";

export default function AgentsPage() {
    const { activeSessionId } = useSessionStore();
    const sessionId = activeSessionId ?? "";

    return (
        <div className="h-full flex flex-col gap-6 p-6">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-3xl font-bold text-gradient mb-2">Agent Orchestration</h1>
                    <p className="text-gray-400">Monitoring real-time backend generation progress.</p>
                </div>
                {sessionId && (
                    <div className="text-xs text-cyan-300 bg-cyan-500/10 px-3 py-1 rounded-full border border-cyan-500/30 font-mono">
                        Session {sessionId.slice(0, 8)}
                    </div>
                )}
            </div>

            {sessionId ? (
                <AgentOrchestrator projectId={sessionId} />
            ) : (
                <div className="rounded-xl border border-white/10 bg-zinc-900/40 p-6 text-sm text-zinc-400">
                    No active session selected. Create or select a BRD session first.
                </div>
            )}
        </div>
    );
}
