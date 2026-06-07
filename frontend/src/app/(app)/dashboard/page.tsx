"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
    AlertTriangle,
    ArrowRight,
    Database,
    Download,
    FileText,
    Loader2,
    Plus,
    Share2,
    TrendingUp,
    Zap,
} from "lucide-react";

import PipelineStepper, { StageInfo } from "@/components/ui/PipelineStepper";
import { ShareBoardModal } from "@/components/ShareBoardModal";
import { getBRD, getChunks } from "@/lib/apiClient";
import { useSessionStore } from "@/store/useSessionStore";
import { useAuth } from "@/contexts/AuthContext";
import type { Board } from "@/lib/firestore/boards";

interface SignalCounts {
    total: number;
    requirement: number;
    decision: number;
    feedback: number;
    timeline: number;
    noise: number;
    lowConfidence: number;
    sources: number;
}

const COLORS: Record<string, string> = {
    Requirement: "#3B82F6",
    Decision: "#8B5CF6",
    Feedback: "#F59E0B",
    Timeline: "#10B981",
    Noise: "#6B7280",
};

function hasGeneratedContent(sections: Record<string, string | undefined>): boolean {
    return Object.values(sections).some((content) => {
        const text = (content ?? "").trim().toLowerCase();
        return text.length > 0 && !text.includes("insufficient data");
    });
}

function DonutChart({
    data,
    onSegmentClick,
    activeSegment,
}: {
    data: Array<{ label: string; count: number; color: string }>;
    onSegmentClick: (label: string | null) => void;
    activeSegment: string | null;
}) {
    const total = data.reduce((sum, item) => sum + item.count, 0);
    const cx = 80;
    const cy = 80;
    const r = 60;
    const stroke = 22;
    const circumference = 2 * Math.PI * r;

    let offset = 0;
    const segments = data.map((d) => {
        const pct = total > 0 ? d.count / total : 0;
        const len = pct * circumference;
        const segment = { ...d, len, offset };
        offset += len;
        return segment;
    });

    return (
        <div className="flex flex-col items-center gap-4">
            <div className="relative">
                <svg width="160" height="160" viewBox="0 0 160 160">
                    <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth={stroke} />
                    {total > 0 &&
                        segments.map((seg) => (
                            <circle
                                key={seg.label}
                                cx={cx}
                                cy={cy}
                                r={r}
                                fill="none"
                                stroke={seg.color}
                                strokeWidth={activeSegment === seg.label ? stroke + 4 : stroke}
                                strokeDasharray={`${seg.len} ${circumference - seg.len}`}
                                strokeDashoffset={-seg.offset}
                                strokeLinecap="round"
                                transform={`rotate(-90 ${cx} ${cy})`}
                                style={{
                                    opacity: activeSegment && activeSegment !== seg.label ? 0.3 : 1,
                                    filter: activeSegment === seg.label ? `drop-shadow(0 0 8px ${seg.color})` : undefined,
                                    cursor: "pointer",
                                    transition: "all 0.2s ease",
                                }}
                                onClick={() => onSegmentClick(activeSegment === seg.label ? null : seg.label)}
                            />
                        ))}
                    <text x={cx} y={cy - 6} textAnchor="middle" className="fill-zinc-100" style={{ fontSize: 22, fontWeight: 700 }}>
                        {total}
                    </text>
                    <text x={cx} y={cy + 12} textAnchor="middle" className="fill-zinc-500" style={{ fontSize: 9 }}>
                        SIGNALS
                    </text>
                </svg>
            </div>

            <div className="w-full space-y-1.5">
                {data.map((d) => (
                    <button
                        key={d.label}
                        onClick={() => onSegmentClick(activeSegment === d.label ? null : d.label)}
                        className={`w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg text-left transition-all ${
                            activeSegment === d.label ? "bg-white/8" : "hover:bg-white/5"
                        }`}
                    >
                        <div className="w-2.5 h-2.5 rounded-sm flex-shrink-0" style={{ background: d.color }} />
                        <span className="text-xs text-zinc-300 flex-1">{d.label}</span>
                        <span className="text-xs font-mono text-zinc-500">{d.count}</span>
                        <span className="text-[10px] text-zinc-600">{total > 0 ? ((d.count / total) * 100).toFixed(0) : 0}%</span>
                    </button>
                ))}
            </div>
        </div>
    );
}

function ActionCentre({
    hasBRDData,
    onShare,
}: {
    hasBRDData: boolean;
    onShare: () => void;
}) {
    return (
        <div className="space-y-3 h-full">
            <div className="glass-card p-4 rounded-xl border-amber-500/20 hover:border-amber-500/30 transition-all">
                <div className="flex items-start gap-3">
                    <div className="w-8 h-8 rounded-lg bg-amber-500/15 flex items-center justify-center flex-shrink-0">
                        <Zap size={16} className="text-amber-400" />
                    </div>
                    <div>
                        <p className="text-sm font-semibold text-amber-300">Pipeline Ready</p>
                        <p className="text-xs text-zinc-500 mt-0.5">Signals classified and stored in AKS</p>
                    </div>
                </div>
            </div>

            <div className="glass-card p-4 rounded-xl">
                <p className="text-xs text-zinc-500 uppercase tracking-wider mb-3 font-medium">Next Actions</p>
                <div className="space-y-2">
                    <Link href="/brd">
                        <button className="btn-primary w-full flex items-center justify-center gap-2 text-sm py-2.5">
                            <FileText size={15} />
                            {hasBRDData ? "View BRD Draft" : "Generate BRD Draft"}
                            <ArrowRight size={14} className="ml-auto opacity-60" />
                        </button>
                    </Link>
                    <button
                        onClick={onShare}
                        disabled={!hasBRDData}
                        className="btn-secondary w-full flex items-center justify-center gap-2 text-sm py-2 mt-1 disabled:opacity-50"
                    >
                        <Share2 size={14} />
                        Share BRD
                    </button>
                    <Link href="/signals">
                        <button className="btn-secondary w-full flex items-center justify-center gap-2 text-sm py-2 mt-1">
                            <AlertTriangle size={14} className="text-amber-400" />
                            Review Signals
                        </button>
                    </Link>
                </div>
            </div>

            <div className="glass-card p-4 rounded-xl">
                <p className="text-xs text-zinc-500 uppercase tracking-wider mb-2 font-medium">Export Status</p>
                <div className="flex items-center gap-2">
                    {hasBRDData ? (
                        <Link href="/export" className="flex items-center gap-2 text-xs text-emerald-400 hover:text-emerald-300 transition-colors">
                            <Download size={13} /> Download BRD
                        </Link>
                    ) : (
                        <>
                            <Download size={13} className="text-zinc-600" />
                            <span className="text-xs text-zinc-500">Awaiting BRD generation</span>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}

export default function DashboardPage() {
    const { activeSessionId, sessions } = useSessionStore();
    const { user } = useAuth();
    const sessionId = activeSessionId ?? "";

    const [activeSegment, setActiveSegment] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [shareOpen, setShareOpen] = useState(false);
    const [flagsCount, setFlagsCount] = useState(0);
    const [hasBRDData, setHasBRDData] = useState(false);
    const [counts, setCounts] = useState<SignalCounts>({
        total: 0,
        requirement: 0,
        decision: 0,
        feedback: 0,
        timeline: 0,
        noise: 0,
        lowConfidence: 0,
        sources: 0,
    });

    const sharedBoards = sessions.filter((s) => s.role && s.role !== "owner");
    const activeSession = sessions.find((s) => s.id === sessionId);
    const boardForShare: Board | null =
        activeSession && sessionId
            ? {
                  id: sessionId,
                  title: activeSession.name ?? "Untitled BRD",
                  description: activeSession.description ?? "",
                  ownerUid: activeSession.role === "owner" ? (user?.uid ?? "") : "shared",
                  status: activeSession.status ?? "draft",
                  createdAt: new Date() as unknown as import("firebase/firestore").Timestamp,
                  updatedAt: new Date() as unknown as import("firebase/firestore").Timestamp,
              }
            : null;

    useEffect(() => {
        const load = async () => {
            if (!sessionId) {
                setCounts({
                    total: 0,
                    requirement: 0,
                    decision: 0,
                    feedback: 0,
                    timeline: 0,
                    noise: 0,
                    lowConfidence: 0,
                    sources: 0,
                });
                setFlagsCount(0);
                setHasBRDData(false);
                return;
            }

            setLoading(true);
            try {
                const [chunkRes, brdRes] = await Promise.all([
                    getChunks(sessionId, "all"),
                    getBRD(sessionId, "markdown").catch(() => null),
                ]);

                const next: SignalCounts = {
                    total: 0,
                    requirement: 0,
                    decision: 0,
                    feedback: 0,
                    timeline: 0,
                    noise: 0,
                    lowConfidence: 0,
                    sources: new Set(chunkRes.chunks.map((c) => c.source_ref)).size,
                };

                chunkRes.chunks.forEach((chunk) => {
                    const label = (chunk.signal_label ?? chunk.label ?? "").toLowerCase();
                    if (chunk.suppressed) {
                        next.noise += 1;
                        return;
                    }
                    next.total += 1;
                    if (label === "requirement") next.requirement += 1;
                    else if (label === "decision") next.decision += 1;
                    else if (label === "stakeholder_feedback" || label === "feedback") next.feedback += 1;
                    else if (label === "timeline_reference" || label === "timeline") next.timeline += 1;
                    if ((chunk.confidence ?? 0) < 0.7) next.lowConfidence += 1;
                });

                setCounts(next);
                setFlagsCount(brdRes?.flags.length ?? 0);
                setHasBRDData(Boolean(brdRes && hasGeneratedContent(brdRes.sections)));
            } finally {
                setLoading(false);
            }
        };

        load();
    }, [sessionId]);

    const signalData = useMemo(
        () => [
            { label: "Requirement", count: counts.requirement, color: COLORS.Requirement },
            { label: "Decision", count: counts.decision, color: COLORS.Decision },
            { label: "Feedback", count: counts.feedback, color: COLORS.Feedback },
            { label: "Timeline", count: counts.timeline, color: COLORS.Timeline },
            { label: "Noise", count: counts.noise, color: COLORS.Noise },
        ],
        [counts]
    );

    const stats = [
        { label: "Sources Connected", value: loading ? "..." : String(counts.sources), icon: Database, color: "text-cyan-400", glow: "shadow-glow-cyan" },
        { label: "Chunks Processed", value: loading ? "..." : String(counts.total + counts.noise), icon: TrendingUp, color: "text-purple-400", glow: "shadow-glow-purple" },
        { label: "Signals Extracted", value: loading ? "..." : String(counts.total), icon: Zap, color: "text-amber-400", glow: "shadow-glow-amber" },
        { label: "Validation Flags", value: loading ? "..." : String(flagsCount), icon: AlertTriangle, color: "text-red-400", glow: "shadow-glow-red" },
    ];

    const pipelineStages: StageInfo[] = [
        { name: "Ingestion", status: counts.total + counts.noise > 0 ? "complete" : "pending", itemCount: counts.total + counts.noise },
        { name: "Noise Filtering", status: counts.total + counts.noise > 0 ? "complete" : "pending", itemCount: counts.total },
        { name: "AKS Storage", status: counts.total > 0 ? "complete" : "pending" },
        { name: "BRD Generation", status: hasBRDData ? "complete" : counts.total > 0 ? "running" : "pending" },
        { name: "Validation", status: hasBRDData ? "complete" : "pending", itemCount: flagsCount },
        { name: "Export", status: hasBRDData ? "running" : "pending" },
    ];

    return (
        <div className="p-6 space-y-6 max-w-[1400px]">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-zinc-100">Session Dashboard</h1>
                    <p className="text-sm text-zinc-500 mt-0.5">
                        {sessionId ? (
                            <span className="font-mono">
                                {sessionId.slice(0, 8)}... - {new Date().toLocaleDateString("en-IN")}
                            </span>
                        ) : (
                            "No active session - create one to get started"
                        )}
                    </p>
                </div>
                <Link href="/ingestion">
                    <button className="btn-primary flex items-center gap-2 text-sm">
                        <Plus size={15} />
                        Add Sources
                    </button>
                </Link>
            </div>

            <motion.div
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4 }}
                className="glass-card p-5 rounded-xl"
            >
                <div className="flex items-center justify-between mb-5">
                    <div>
                        <h2 className="text-sm font-semibold text-zinc-200">Pipeline Status</h2>
                        <p className="text-xs text-zinc-500 mt-0.5">Derived from live backend session state</p>
                    </div>
                    <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full glass-card text-[11px]">
                        {loading ? (
                            <>
                                <Loader2 size={10} className="animate-spin text-zinc-400" />
                                <span className="text-zinc-400">Loading</span>
                            </>
                        ) : counts.total > 0 ? (
                            <>
                                <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                                <span className="text-emerald-300 font-medium">Ready</span>
                            </>
                        ) : (
                            <>
                                <div className="w-1.5 h-1.5 rounded-full bg-zinc-500" />
                                <span className="text-zinc-400 font-medium">Idle</span>
                            </>
                        )}
                    </div>
                </div>
                <PipelineStepper stages={pipelineStages} variant="expanded" />
            </motion.div>

            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                {stats.map((stat, i) => {
                    const Icon = stat.icon;
                    return (
                        <motion.div
                            key={stat.label}
                            initial={{ opacity: 0, y: 16 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.4, delay: i * 0.06 }}
                            className="glass-card p-4 rounded-xl flex items-center gap-3"
                        >
                            <div className={`w-10 h-10 rounded-lg bg-white/5 flex items-center justify-center flex-shrink-0 ${stat.glow}`}>
                                <Icon size={18} className={stat.color} />
                            </div>
                            <div>
                                <p className="text-2xl font-bold text-zinc-100">{stat.value}</p>
                                <p className="text-[11px] text-zinc-500 leading-tight">{stat.label}</p>
                            </div>
                        </motion.div>
                    );
                })}
            </div>

            <div className="grid lg:grid-cols-3 gap-5">
                <motion.div
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.4, delay: 0.25 }}
                    className="glass-card p-5 rounded-xl"
                >
                    <div className="flex items-center justify-between mb-4">
                        <h2 className="text-sm font-semibold text-zinc-200">Signal Breakdown</h2>
                        {activeSegment && (
                            <button onClick={() => setActiveSegment(null)} className="text-[11px] text-cyan-400 hover:text-cyan-300 transition-colors">
                                Clear filter
                            </button>
                        )}
                    </div>
                    {loading ? (
                        <div className="flex items-center justify-center py-16 gap-2 text-zinc-500 text-xs">
                            <Loader2 size={14} className="animate-spin" /> Loading signals...
                        </div>
                    ) : (
                        <DonutChart data={signalData} onSegmentClick={setActiveSegment} activeSegment={activeSegment} />
                    )}
                    {activeSegment && (
                        <div className="mt-3 px-3 py-2 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-xs text-cyan-300">
                            Signals filtered to <strong>{activeSegment}</strong> - go to{" "}
                            <Link href="/signals" className="underline hover:text-cyan-200">
                                Signal Review
                            </Link>
                        </div>
                    )}
                </motion.div>

                <motion.div
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.4, delay: 0.32 }}
                    className="glass-card p-5 rounded-xl lg:col-span-2"
                >
                    <h2 className="text-sm font-semibold text-zinc-200 mb-4">Action Centre</h2>
                    <ActionCentre hasBRDData={hasBRDData} onShare={() => setShareOpen(true)} />
                </motion.div>
            </div>

            {sharedBoards.length > 0 && (
                <motion.div
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.4, delay: 0.4 }}
                    className="glass-card p-5 rounded-xl"
                >
                    <div className="flex items-center gap-2 mb-4">
                        <Share2 size={14} className="text-cyan-400" />
                        <h2 className="text-sm font-semibold text-zinc-200">Shared with me</h2>
                        <span className="glass-badge bg-white/5 border-white/10 text-zinc-400 ml-auto">
                            {sharedBoards.length} board{sharedBoards.length !== 1 ? "s" : ""}
                        </span>
                    </div>
                    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
                        {sharedBoards.map((b) => (
                            <Link
                                key={b.id}
                                href="/brd"
                                onClick={() => useSessionStore.getState().setActive(b.id)}
                                className="glass-card p-4 rounded-xl hover:border-white/20 transition-all group block"
                            >
                                <div className="flex items-start justify-between gap-2 mb-2">
                                    <p className="text-sm font-medium text-zinc-100 group-hover:text-white transition-colors truncate">{b.name}</p>
                                    <span
                                        className={`glass-badge text-[9px] flex-shrink-0 ${
                                            b.role === "editor"
                                                ? "bg-cyan-500/10 border-cyan-500/30 text-cyan-300"
                                                : "bg-zinc-700/30 border-zinc-600/30 text-zinc-400"
                                        }`}
                                    >
                                        {b.role}
                                    </span>
                                </div>
                                <p className="text-[10px] font-mono text-zinc-600 truncate">{b.id}</p>
                                <div className="flex items-center gap-1 mt-3 text-xs text-zinc-500 group-hover:text-cyan-400 transition-colors">
                                    <ArrowRight size={12} />
                                    <span>Open BRD</span>
                                </div>
                            </Link>
                        ))}
                    </div>
                </motion.div>
            )}

            {boardForShare && <ShareBoardModal board={boardForShare} isOpen={shareOpen} onClose={() => setShareOpen(false)} />}
        </div>
    );
}
