"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import {
    AlertTriangle,
    Bell,
    Check,
    ChevronDown,
    ChevronRight,
    Clock,
    Database,
    Download,
    FileText,
    LayoutDashboard,
    Loader2,
    LogOut,
    Menu,
    Pencil,
    Plus,
    Settings,
    User,
    Wifi,
    WifiOff,
    X,
    Zap,
} from "lucide-react";

import { cn } from "@/lib/utils";
import PipelineStepper, { StageInfo } from "@/components/ui/PipelineStepper";
import NewBRDModal from "@/components/ui/NewBRDModal";
import { useAuthStore } from "@/store/useAuthStore";
import { useAuth } from "@/contexts/AuthContext";
import { useSessionStore } from "@/store/useSessionStore";
import { getBRD, getChunks, type ValidationFlag } from "@/lib/apiClient";

const navigation = [
    { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard, stageIndex: -1 },
    { name: "Sources", href: "/ingestion", icon: Database, stageIndex: 0 },
    { name: "Signals", href: "/signals", icon: Zap, stageIndex: 1 },
    { name: "BRD Draft", href: "/brd", icon: FileText, stageIndex: 3 },
    { name: "Export", href: "/export", icon: Download, stageIndex: 5 },
    { name: "Settings", href: "/settings", icon: Settings, stageIndex: -1 },
];

const EMPTY_STAGES: StageInfo[] = [
    { name: "Ingestion", status: "pending" },
    { name: "Noise Filtering", status: "pending" },
    { name: "AKS Storage", status: "pending" },
    { name: "BRD Generation", status: "pending" },
    { name: "Validation", status: "pending" },
    { name: "Export", status: "pending" },
];

const STATUS_DOT: Record<string, string> = {
    complete: "bg-emerald-400",
    running: "bg-amber-400 animate-pulse",
    pending: "bg-zinc-600",
    error: "bg-red-400",
    none: "hidden",
};

function getNavStatus(stageIndex: number, stages: StageInfo[]): "complete" | "running" | "pending" | "error" | "none" {
    if (stageIndex < 0) {
        return "none";
    }
    return stages[stageIndex]?.status ?? "pending";
}

function SessionSelector({ onNewBRD }: { onNewBRD: () => void }) {
    const [open, setOpen] = useState(false);
    const [renamingId, setRenamingId] = useState<string | null>(null);
    const [renameValue, setRenameValue] = useState("");
    const [renameLoading, setRenameLoading] = useState(false);
    const [hasHydrated, setHasHydrated] = useState(false);
    const ref = useRef<HTMLDivElement>(null);
    const renameInputRef = useRef<HTMLInputElement>(null);
    const { sessions, activeSessionId, setActive, renameSession } = useSessionStore();
    const { user } = useAuth();

    useEffect(() => {
        setHasHydrated(true);
        const onMouseDown = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) {
                setOpen(false);
                setRenamingId(null);
            }
        };
        document.addEventListener("mousedown", onMouseDown);
        return () => document.removeEventListener("mousedown", onMouseDown);
    }, []);

    useEffect(() => {
        if (renamingId !== null) {
            // Focus the input after render
            setTimeout(() => renameInputRef.current?.focus(), 50);
        }
    }, [renamingId]);

    const active = sessions.find((s) => s.id === activeSessionId) ?? sessions[0];
    if (!hasHydrated || !active) {
        return <div className="w-full h-[46px] rounded-lg bg-white/5 animate-pulse" />;
    }

    const startRename = (e: React.MouseEvent, sess: typeof active) => {
        e.stopPropagation();
        setRenamingId(sess.id);
        setRenameValue(sess.name);
    };

    const commitRename = async (e?: React.MouseEvent) => {
        e?.stopPropagation();
        if (!renamingId || !renameValue.trim() || !user) return;
        const trimmed = renameValue.trim();
        const current = sessions.find((s) => s.id === renamingId);
        if (current && current.name === trimmed) {
            setRenamingId(null);
            return;
        }
        setRenameLoading(true);
        try {
            await renameSession(renamingId, user.uid, trimmed);
        } catch {
            // silently fail — keep old name
        } finally {
            setRenameLoading(false);
            setRenamingId(null);
        }
    };

    const cancelRename = (e: React.MouseEvent) => {
        e.stopPropagation();
        setRenamingId(null);
    };

    const handleRenameKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "Enter") {
            e.preventDefault();
            commitRename();
        } else if (e.key === "Escape") {
            e.preventDefault();
            setRenamingId(null);
        }
    };

    return (
        <div ref={ref} className="relative">
            <button
                onClick={() => setOpen((v) => !v)}
                className="w-full flex items-center justify-between px-3 py-2.5 glass-card rounded-lg group hover:border-white/20 transition-all"
            >
                <div className="flex items-center gap-2 min-w-0">
                    <Clock size={12} className="text-zinc-500 flex-shrink-0" />
                    <div className="min-w-0 text-left">
                        <p className="text-xs font-medium text-zinc-200 truncate">{active.name}</p>
                        <p className="text-[10px] text-zinc-500 font-mono">{active.id}</p>
                    </div>
                </div>
                <ChevronDown size={12} className={cn("text-zinc-500 flex-shrink-0 transition-transform", open && "rotate-180")} />
            </button>

            <AnimatePresence>
                {open && (
                    <motion.div
                        initial={{ opacity: 0, y: -6, scale: 0.97 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: -6, scale: 0.97 }}
                        transition={{ duration: 0.15 }}
                        className="absolute top-full left-0 right-0 mt-1.5 z-50 rounded-xl overflow-hidden"
                        style={{
                            background: "rgba(10,10,10,0.99)",
                            border: "1px solid rgba(255,255,255,0.10)",
                            boxShadow: "0 20px 60px rgba(0,0,0,0.6)",
                        }}
                    >
                        <div className="p-1.5 max-h-[240px] overflow-y-auto">
                            {sessions.map((sess) => (
                                <div key={sess.id} className="relative group/item">
                                    {renamingId === sess.id ? (
                                        /* ── Inline rename input ── */
                                        <div className="flex items-center gap-1.5 px-2 py-1.5" onClick={(e) => e.stopPropagation()}>
                                            <input
                                                ref={renameInputRef}
                                                type="text"
                                                value={renameValue}
                                                onChange={(e) => setRenameValue(e.target.value)}
                                                onKeyDown={handleRenameKeyDown}
                                                disabled={renameLoading}
                                                className="flex-1 min-w-0 text-xs bg-zinc-800 border border-white/15 rounded-md px-2 py-1.5 text-zinc-100 outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/20 disabled:opacity-50"
                                                placeholder="Session name"
                                                maxLength={80}
                                            />
                                            <button
                                                onClick={commitRename}
                                                disabled={renameLoading || !renameValue.trim()}
                                                className="w-6 h-6 rounded-md bg-emerald-500/15 border border-emerald-500/25 flex items-center justify-center text-emerald-400 hover:bg-emerald-500/25 transition-colors flex-shrink-0 disabled:opacity-40"
                                                title="Save"
                                            >
                                                {renameLoading ? (
                                                    <Loader2 size={10} className="animate-spin" />
                                                ) : (
                                                    <Check size={10} />
                                                )}
                                            </button>
                                            <button
                                                onClick={cancelRename}
                                                disabled={renameLoading}
                                                className="w-6 h-6 rounded-md bg-white/5 border border-white/10 flex items-center justify-center text-zinc-400 hover:bg-white/10 transition-colors flex-shrink-0 disabled:opacity-40"
                                                title="Cancel"
                                            >
                                                <X size={10} />
                                            </button>
                                        </div>
                                    ) : (
                                        /* ── Default session row ── */
                                        <button
                                            onClick={() => {
                                                setActive(sess.id);
                                                setOpen(false);
                                            }}
                                            className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg hover:bg-white/6 text-left transition-colors group/row"
                                        >
                                            <div
                                                className={cn(
                                                    "w-1.5 h-1.5 rounded-full flex-shrink-0",
                                                    sess.status === "active" || sess.status === "draft" ? "bg-emerald-400" : "bg-zinc-600"
                                                )}
                                            />
                                            <div className="flex-1 min-w-0">
                                                <p className="text-xs text-zinc-200 truncate">{sess.name}</p>
                                                <p className="text-[10px] text-zinc-600 font-mono">{sess.id}</p>
                                            </div>
                                            {sess.id === active.id && <Check size={11} className="text-zinc-300 flex-shrink-0" />}
                                            <span
                                                onClick={(e) => startRename(e, sess)}
                                                className="opacity-0 group-hover/row:opacity-100 p-1 rounded hover:bg-white/10 text-zinc-500 hover:text-zinc-200 transition-all flex-shrink-0"
                                                title="Rename session"
                                            >
                                                <Pencil size={10} />
                                            </span>
                                        </button>
                                    )}
                                </div>
                            ))}
                        </div>

                        <div className="border-t border-white/8 p-1.5">
                            <button
                                onClick={() => {
                                    setOpen(false);
                                    onNewBRD();
                                }}
                                className="w-full flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-white/6 text-left transition-colors group"
                            >
                                <div className="w-5 h-5 rounded-md bg-white/10 border border-white/20 flex items-center justify-center flex-shrink-0">
                                    <Plus size={10} className="text-zinc-300" />
                                </div>
                                <span className="text-xs text-zinc-300 font-medium group-hover:text-white transition-colors">New BRD Session...</span>
                            </button>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}

function hasGeneratedContent(sections: Record<string, string | undefined>): boolean {
    return Object.values(sections).some((content) => {
        const normalized = (content ?? "").trim().toLowerCase();
        return normalized.length > 0 && !normalized.includes("insufficient data");
    });
}

export default function DashboardShell({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const router = useRouter();
    const { user } = useAuthStore();
    const { logout } = useAuth();
    const { activeSessionId } = useSessionStore();

    const [sidebarOpen, setSidebarOpen] = useState(true);
    const [modalOpen, setModalOpen] = useState(false);
    const [apiConnected, setApiConnected] = useState(false);
    const [signalCount, setSignalCount] = useState(0);
    const [flagCount, setFlagCount] = useState(0);
    const [flags, setFlags] = useState<ValidationFlag[]>([]);
    const [notifOpen, setNotifOpen] = useState(false);
    const notifRef = useRef<HTMLDivElement>(null);
    const [stages, setStages] = useState<StageInfo[]>(EMPTY_STAGES);

    useEffect(() => {
        const checkApi = async () => {
            const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
            try {
                const res = await fetch(`${base.replace(/\/$/, "")}/`);
                setApiConnected(res.ok);
            } catch {
                setApiConnected(false);
            }
        };

        checkApi();
        const timer = window.setInterval(checkApi, 30000);
        return () => window.clearInterval(timer);
    }, []);

    useEffect(() => {
        const onMouseDown = (e: MouseEvent) => {
            if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
                setNotifOpen(false);
            }
        };
        document.addEventListener("mousedown", onMouseDown);
        return () => document.removeEventListener("mousedown", onMouseDown);
    }, []);

    useEffect(() => {
        const loadStageStatus = async () => {
            if (!activeSessionId) {
                setSignalCount(0);
                setFlagCount(0);
                setFlags([]);
                setStages(EMPTY_STAGES);
                return;
            }

            let chunkTotal = 0;
            let activeTotal = 0;
            let noiseTotal = 0;
            let brdReady = false;
            let validationFlagCount = 0;

            try {
                const chunkRes = await getChunks(activeSessionId, "all");
                chunkTotal = chunkRes.count;
                const active = chunkRes.chunks.filter((c) => !c.suppressed);
                activeTotal = active.length;
                noiseTotal = chunkRes.chunks.length - active.length;
            } catch {
                setSignalCount(0);
            }

            try {
                const brd = await getBRD(activeSessionId, "markdown");
                brdReady = hasGeneratedContent(brd.sections);
                setFlags(brd.flags);
                setFlagCount(brd.flags.length);
            } catch {
                brdReady = false;
                setFlags([]);
                setFlagCount(0);
            }

            setSignalCount(activeTotal);
            setStages([
                { name: "Ingestion", status: chunkTotal > 0 ? "complete" : "pending", itemCount: chunkTotal },
                { name: "Noise Filtering", status: chunkTotal > 0 ? "complete" : "pending", itemCount: activeTotal },
                { name: "AKS Storage", status: activeTotal > 0 ? "complete" : "pending", itemCount: activeTotal },
                { name: "BRD Generation", status: brdReady ? "complete" : activeTotal > 0 ? "running" : "pending" },
                { name: "Validation", status: brdReady ? "complete" : "pending", itemCount: validationFlagCount },
                { name: "Export", status: brdReady ? "running" : "pending", itemCount: noiseTotal },
            ]);
        };

        loadStageStatus();
    }, [activeSessionId, pathname]);

    const activeStage = useMemo(() => stages.find((s) => s.status === "running"), [stages]);

    const handleLogout = async () => {
        try {
            await logout();
        } finally {
            // Force hard navigation to root "/" to ensure clean state and avoid middleware loops.
            window.location.href = "/";
        }
    };

    return (
        <>
            <NewBRDModal open={modalOpen} onClose={() => setModalOpen(false)} />
            <div className="flex h-screen overflow-hidden" style={{ background: "var(--bg-base)" }}>
                <AnimatePresence initial={false}>
                    {sidebarOpen && (
                        <motion.aside
                            key="sidebar"
                            initial={{ width: 0, opacity: 0 }}
                            animate={{ width: 240, opacity: 1 }}
                            exit={{ width: 0, opacity: 0 }}
                            transition={{ type: "spring", damping: 28, stiffness: 240 }}
                            className="glass-sidebar flex flex-col h-full overflow-hidden z-30 flex-shrink-0"
                        >
                            <div className="px-5 py-5 border-b border-white/8">
                                <div className="flex items-center gap-2 mb-4">
                                    <div className="w-8 h-8 rounded-lg bg-white/10 border border-white/20 flex items-center justify-center glow-white">
                                        <Zap size={14} className="text-white" />
                                    </div>
                                    <div>
                                        <h1 className="text-sm font-bold text-white leading-none tracking-tight">Beacon</h1>
                                        <p className="text-[10px] text-zinc-400 font-medium">BRD Agent</p>
                                    </div>
                                </div>
                                <SessionSelector onNewBRD={() => setModalOpen(true)} />
                            </div>

                            <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
                                <div className="px-2 mb-4">
                                    <button
                                        onClick={() => setModalOpen(true)}
                                        className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl bg-white text-zinc-950 font-semibold text-sm hover:bg-zinc-200 transition-all shadow-[0_4px_12px_rgba(255,255,255,0.1)] active:scale-[0.98]"
                                    >
                                        <Plus size={16} />
                                        <span>New BRD Session</span>
                                    </button>
                                </div>

                                {navigation.map((item) => {
                                    const isActive = pathname === item.href || pathname?.startsWith(`${item.href}/`);
                                    const Icon = item.icon;
                                    const status = getNavStatus(item.stageIndex, stages);

                                    return (
                                        <Link
                                            key={item.name}
                                            href={item.href}
                                            className={cn(
                                                "group flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all relative",
                                                isActive ? "nav-item-active" : "text-zinc-400 hover:text-zinc-100 hover:bg-white/5"
                                            )}
                                        >
                                            {isActive && (
                                                <motion.div
                                                    layoutId="sidebar-active"
                                                    className="absolute inset-0 rounded-lg bg-white/6"
                                                    transition={{ type: "spring", stiffness: 380, damping: 35 }}
                                                />
                                            )}
                                            <Icon size={16} className="relative z-10 flex-shrink-0" />
                                            <span className="relative z-10 flex-1 truncate">{item.name}</span>
                                            {status !== "none" && (
                                                <span className={cn("w-1.5 h-1.5 rounded-full relative z-10 flex-shrink-0", STATUS_DOT[status])} />
                                            )}
                                        </Link>
                                    );
                                })}
                            </nav>

                            <div className="px-4 pb-4 space-y-3 border-t border-white/8 pt-3">
                                {activeStage && (
                                    <div className="px-3 py-2 rounded-lg glass-card">
                                        <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Active Stage</p>
                                        <div className="flex items-center gap-2">
                                            <div className="w-1.5 h-1.5 rounded-full bg-white/60 animate-pulse flex-shrink-0" />
                                            <span className="text-xs font-medium text-zinc-300">{activeStage.name}</span>
                                        </div>
                                    </div>
                                )}

                                <div className="flex items-center justify-between px-1">
                                    <div className="flex items-center gap-1.5">
                                        {apiConnected ? <Wifi size={12} className="text-emerald-400" /> : <WifiOff size={12} className="text-red-400" />}
                                        <span className="text-[10px] text-zinc-500">Backend {apiConnected ? "Connected" : "Disconnected"}</span>
                                    </div>
                                    <div className={cn("w-1.5 h-1.5 rounded-full", apiConnected ? "bg-emerald-400" : "bg-red-400")} />
                                </div>

                                <Link
                                    href="/profile"
                                    className="flex items-center gap-2.5 px-2 py-2 rounded-lg glass-card hover:bg-white/5 transition-all group/user"
                                >
                                    {user?.photoURL ? (
                                        <img
                                            src={user.photoURL}
                                            alt={user.name || "User"}
                                            className="w-7 h-7 rounded-full object-cover flex-shrink-0 border border-white/25 group-hover/user:border-white/40 transition-colors"
                                        />
                                    ) : (
                                        <div className="w-7 h-7 rounded-full bg-white/10 border border-white/20 flex items-center justify-center flex-shrink-0 group-hover/user:border-white/40 transition-colors">
                                            <User size={12} className="text-zinc-200" />
                                        </div>
                                    )}
                                    <div className="flex-1 min-w-0">
                                        <p className="text-xs font-medium text-zinc-200 truncate group-hover/user:text-white transition-colors">{user?.name ?? "User"}</p>
                                        <p className="text-[10px] text-zinc-500 truncate">{user?.email ?? ""}</p>
                                    </div>
                                    <button
                                        onClick={(e) => {
                                            e.preventDefault();
                                            handleLogout();
                                        }}
                                        title="Logout"
                                        className="p-1 rounded text-zinc-600 hover:text-red-400 transition-colors flex-shrink-0 relative z-10"
                                    >
                                        <LogOut size={12} />
                                    </button>
                                </Link>
                            </div>
                        </motion.aside>
                    )}
                </AnimatePresence>

                <div className="flex-1 flex flex-col overflow-hidden min-w-0">
                    <header className="glass-topbar h-12 flex items-center justify-between px-3 sm:px-4 flex-shrink-0 z-20 gap-2 sm:gap-3">
                        <div className="flex items-center gap-2 sm:gap-3 min-w-0">
                            <button
                                onClick={() => setSidebarOpen((v) => !v)}
                                className="p-1 sm:p-1.5 rounded-lg text-zinc-500 hover:text-zinc-200 hover:bg-white/5 transition-colors flex-shrink-0"
                            >
                                {sidebarOpen ? <X size={14} /> : <Menu size={14} />}
                            </button>

                            <span className="font-mono text-[9px] sm:text-[11px] text-zinc-600 hidden md:block truncate">
                                {activeSessionId ? activeSessionId : "No active session"}
                            </span>

                            <div className="hidden sm:flex items-center gap-1 sm:gap-1.5 text-[10px] sm:text-xs text-zinc-500 truncate">
                                <Link href="/" className="hover:text-zinc-300 transition-colors truncate">
                                    Home
                                </Link>
                                {pathname && pathname !== "/" && (
                                    <>
                                        <ChevronRight size={10} className="text-zinc-700 flex-shrink-0" />
                                        <span className="text-zinc-300 capitalize truncate">{pathname.split("/").filter(Boolean).at(-1)}</span>
                                    </>
                                )}
                            </div>
                        </div>

                        <div className="flex items-center gap-1 sm:gap-2 lg:gap-3">
                            <PipelineStepper stages={stages} variant="compact" className="hidden lg:flex" />

                            <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full glass-card text-[10px] sm:text-[11px]">
                                <Zap size={10} className="text-zinc-400" />
                                <span className="text-zinc-400 hidden md:inline">{signalCount} signals</span>
                            </div>

                            <div ref={notifRef} className="relative flex-shrink-0">
                                <button
                                    onClick={() => setNotifOpen((v) => !v)}
                                    className="relative p-1 sm:p-1.5 rounded-lg text-zinc-500 hover:text-zinc-200 hover:bg-white/5 transition-colors"
                                >
                                    <Bell size={14} />
                                    {flagCount > 0 && (
                                        <span className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-red-500 rounded-full flex items-center justify-center text-[8px] font-bold text-white">
                                            {flagCount}
                                        </span>
                                    )}
                                </button>

                                <AnimatePresence>
                                    {notifOpen && (
                                        <motion.div
                                            initial={{ opacity: 0, y: -6, scale: 0.97 }}
                                            animate={{ opacity: 1, y: 0, scale: 1 }}
                                            exit={{ opacity: 0, y: -6, scale: 0.97 }}
                                            transition={{ duration: 0.15 }}
                                            className="absolute right-0 top-full mt-2 z-50 w-80 sm:w-[340px] rounded-xl overflow-hidden"
                                            style={{
                                                background: "rgba(10,10,10,0.99)",
                                                border: "1px solid rgba(255,255,255,0.10)",
                                                boxShadow: "0 20px 60px rgba(0,0,0,0.6)",
                                            }}
                                        >
                                            <div className="px-4 py-3 border-b border-white/8 flex items-center justify-between">
                                                <div className="flex items-center gap-2">
                                                    <AlertTriangle size={13} className="text-zinc-400" />
                                                    <span className="text-xs font-semibold text-zinc-200">Alerts</span>
                                                </div>
                                                {flagCount > 0 && (
                                                    <span className="text-[10px] font-bold text-zinc-400 bg-white/6 px-2 py-0.5 rounded-full">
                                                        {flagCount} {flagCount === 1 ? "issue" : "issues"}
                                                    </span>
                                                )}
                                            </div>

                                            <div className="max-h-[320px] overflow-y-auto">
                                                {flags.length === 0 ? (
                                                    <div className="px-4 py-8 text-center">
                                                        <Bell size={20} className="text-zinc-700 mx-auto mb-2" />
                                                        <p className="text-xs text-zinc-500">No alerts</p>
                                                        <p className="text-[10px] text-zinc-600 mt-0.5">Validation flags will appear here</p>
                                                    </div>
                                                ) : (
                                                    <div className="p-1.5 space-y-0.5">
                                                        {flags.map((flag, i) => (
                                                            <div
                                                                key={`${flag.section_name}-${flag.flag_type}-${i}`}
                                                                className="px-3 py-2.5 rounded-lg hover:bg-white/5 transition-colors"
                                                            >
                                                                <div className="flex items-start gap-2.5">
                                                                    <div className="mt-0.5 flex-shrink-0">
                                                                        {flag.severity === "high" ? (
                                                                            <div className="w-5 h-5 rounded-md bg-red-500/10 border border-red-500/20 flex items-center justify-center">
                                                                                <AlertTriangle size={10} className="text-red-400" />
                                                                            </div>
                                                                        ) : flag.severity === "medium" ? (
                                                                            <div className="w-5 h-5 rounded-md bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
                                                                                <AlertTriangle size={10} className="text-amber-400" />
                                                                            </div>
                                                                        ) : (
                                                                            <div className="w-5 h-5 rounded-md bg-blue-500/10 border border-blue-500/20 flex items-center justify-center">
                                                                                <AlertTriangle size={10} className="text-blue-400" />
                                                                            </div>
                                                                        )}
                                                                    </div>
                                                                    <div className="flex-1 min-w-0">
                                                                        <div className="flex items-center gap-1.5 mb-0.5">
                                                                            <span className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider">
                                                                                {flag.section_name.replace(/_/g, " ")}
                                                                            </span>
                                                                            <span className={cn(
                                                                                "text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded",
                                                                                flag.severity === "high" && "bg-red-500/10 text-red-400 border border-red-500/20",
                                                                                flag.severity === "medium" && "bg-amber-500/10 text-amber-400 border border-amber-500/20",
                                                                                flag.severity === "low" && "bg-blue-500/10 text-blue-400 border border-blue-500/20",
                                                                            )}>
                                                                                {flag.severity}
                                                                            </span>
                                                                        </div>
                                                                        <p className="text-[11px] text-zinc-300 leading-snug">{flag.description}</p>
                                                                        <p className="text-[10px] text-zinc-600 mt-0.5">{flag.flag_type}</p>
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        ))}
                                                    </div>
                                                )}
                                            </div>

                                            {flags.length > 0 && (
                                                <div className="px-4 py-2.5 border-t border-white/8">
                                                    <p className="text-[10px] text-zinc-600 text-center">
                                                        Flags are generated during BRD validation
                                                    </p>
                                                </div>
                                            )}
                                        </motion.div>
                                    )}
                                </AnimatePresence>
                            </div>
                        </div>
                    </header>

                    <main className="flex-1 overflow-y-auto">{children}</main>
                </div>
            </div>
        </>
    );
}
