"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
    Calendar,
    CheckCircle2,
    FileText,
    Mail,
    MessageSquare,
    Settings as SettingsIcon,
    Users as UsersIcon,
    Video,
    XCircle,
    Loader2,
    Database,
    Hash,
    RefreshCw,
    ArrowRight,
} from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { GmailLogo } from "@/components/icons/GmailLogo";
import { SlackLogo } from "@/components/icons/SlackLogo";

import { useAuthStore } from "@/store/useAuthStore";
import { useIntegrationStore } from "@/store/useIntegrationStore";
import { useSessionStore } from "@/store/useSessionStore";
import {
    disconnectSlack,
    getSlackOAuthUrl,
    getSlackStatus,
    getChunks,
    ingestSlackChannels,
    listSlackChannels,
    getGmailStatus,
    getGmailOAuthUrl,
    disconnectGmail,
    listGmailEmails,
    ingestGmailEmails,
    openGmailAuthPopup,
    type SlackChannel,
    type SlackStatus,
    type GmailEmail,
    type GmailStatus,
} from "@/lib/apiClient";

const dataSources = [
    {
        id: "slack",
        name: "Slack",
        icon: MessageSquare,
        color: "from-purple-500 to-pink-500",
        description: "Connect your Slack workspace to ingest conversations",
        available: true,
    },
    {
        id: "gmail",
        name: "Gmail",
        icon: Mail,
        color: "from-red-500 to-orange-500",
        description: "Sync email threads and discussions",
        available: true,
    },
];

export default function ProfilePage() {
    const searchParams = useSearchParams();
    const { user, updateUser } = useAuthStore();

    useEffect(() => {
        if (typeof window !== "undefined" && window.opener) {
            const gmailParam = searchParams.get("gmail");
            const gmailReason = searchParams.get("reason");
            if (gmailParam) {
                window.opener.postMessage({
                    type: "GMAIL_AUTH_COMPLETE",
                    status: gmailParam,
                    reason: gmailReason
                }, window.location.origin);
                window.close();
            }
        }
    }, [searchParams]);

    const isPopup = typeof window !== "undefined" && window.opener && searchParams.get("gmail");
    if (isPopup) {
        return (
            <div className="fixed inset-0 bg-zinc-950 flex flex-col items-center justify-center p-6 text-center">
                <Loader2 size={32} className="text-cyan-400 animate-spin mb-4" />
                <p className="text-sm text-zinc-300 font-medium">Completing Gmail authentication...</p>
            </div>
        );
    }
    const { integrations, updateIntegration } = useIntegrationStore();
    const { activeSessionId, sessions, setActive } = useSessionStore();

    const [editingProfile, setEditingProfile] = useState(false);
    const [slackStatus, setSlackStatus] = useState<SlackStatus | null>(null);
    const [slackChannels, setSlackChannels] = useState<SlackChannel[]>([]);
    const [selectedSlackChannels, setSelectedSlackChannels] = useState<string[]>([]);
    const [slackLoading, setSlackLoading] = useState(false);
    const [slackIngesting, setSlackIngesting] = useState(false);
    const [slackError, setSlackError] = useState<string | null>(null);
    const [slackMessage, setSlackMessage] = useState<string | null>(null);

    const [gmailStatus, setGmailStatus] = useState<GmailStatus | null>(null);
    const [gmailEmails, setGmailEmails] = useState<GmailEmail[]>([]);
    const [selectedGmailEmails, setSelectedGmailEmails] = useState<string[]>([]);
    const [gmailLoading, setGmailLoading] = useState(false);
    const [gmailIngesting, setGmailIngesting] = useState(false);
    const [gmailError, setGmailError] = useState<string | null>(null);
    const [gmailMessage, setGmailMessage] = useState<string | null>(null);

    const [totalChunks, setTotalChunks] = useState(0);
    const [activeChunks, setActiveChunks] = useState(0);
    const [noiseChunks, setNoiseChunks] = useState(0);
    const [statsLoading, setStatsLoading] = useState(false);

    const activeSources = useMemo(() => (slackStatus?.connected ? 1 : 0) + (gmailStatus?.connected ? 1 : 0), [slackStatus?.connected, gmailStatus?.connected]);
    const relevancePct = totalChunks > 0 ? Math.round((activeChunks / totalChunks) * 100) : 0;

    const syncSlackStatus = async () => {
        setSlackLoading(true);
        setSlackError(null);
        try {
            const status = await getSlackStatus();
            setSlackStatus(status);

            if (status.connected) {
                const channelRes = await listSlackChannels();
                setSlackChannels(channelRes.channels);

                const persisted = integrations.find((i) => i.type === "slack")?.config?.channels ?? [];
                const validSelected = persisted.filter((id) => channelRes.channels.some((c) => c.id === id));
                setSelectedSlackChannels(validSelected);

                const slackIntegration = integrations.find((i) => i.type === "slack");
                if (slackIntegration) {
                    updateIntegration(slackIntegration.id, {
                        connected: true,
                        name: status.team_name ? `${status.team_name} Workspace` : "Slack Workspace",
                        config: {
                            ...(slackIntegration.config ?? {}),
                            workspace: status.team_name ?? "",
                            channels: validSelected,
                        },
                    });
                }
            } else {
                setSlackChannels([]);
                setSelectedSlackChannels([]);

                const slackIntegration = integrations.find((i) => i.type === "slack");
                if (slackIntegration) {
                    updateIntegration(slackIntegration.id, {
                        connected: false,
                        config: {
                            ...(slackIntegration.config ?? {}),
                            workspace: "",
                            channels: [],
                        },
                    });
                }
            }
        } catch (e) {
            setSlackError(e instanceof Error ? e.message : "Failed to load Slack status");
        } finally {
            setSlackLoading(false);
        }
    };

    const syncGmailStatus = async () => {
        setGmailLoading(true);
        setGmailError(null);
        try {
            const status = await getGmailStatus();
            setGmailStatus(status);

            if (status.connected) {
                const emailsRes = await listGmailEmails({ count: 20 });
                setGmailEmails(emailsRes.emails);

                const gmailIntegration = integrations.find((i) => i.type === "gmail");
                if (gmailIntegration) {
                    updateIntegration(gmailIntegration.id, {
                        connected: true,
                    });
                }
            } else {
                const gmailIntegration = integrations.find((i) => i.type === "gmail");
                if (gmailIntegration) {
                    updateIntegration(gmailIntegration.id, {
                        connected: false,
                    });
                }
            }
        } catch (e) {
            setGmailError(e instanceof Error ? e.message : "Failed to load Gmail status");
        } finally {
            setGmailLoading(false);
        }
    };

    const loadSessionStats = async () => {
        if (!activeSessionId) {
            setTotalChunks(0);
            setActiveChunks(0);
            setNoiseChunks(0);
            return;
        }

        setStatsLoading(true);
        try {
            const all = await getChunks(activeSessionId, "all");
            const active = all.chunks.filter((chunk) => !chunk.suppressed).length;
            const noise = all.chunks.length - active;
            setTotalChunks(all.count);
            setActiveChunks(active);
            setNoiseChunks(noise);
        } catch {
            setTotalChunks(0);
            setActiveChunks(0);
            setNoiseChunks(0);
        } finally {
            setStatsLoading(false);
        }
    };

    useEffect(() => {
        syncSlackStatus();
        syncGmailStatus();
    }, []);

    useEffect(() => {
        loadSessionStats();
    }, [activeSessionId]);

    useEffect(() => {
        const slackParam = searchParams.get("slack");
        if (slackParam) {
            if (slackParam === "connected") {
                setSlackMessage("Slack workspace connected successfully.");
                syncSlackStatus();
            } else if (slackParam === "error") {
                setSlackError("Slack OAuth failed. Please try again.");
            }
        }

        const gmailParam = searchParams.get("gmail");
        if (gmailParam) {
            if (gmailParam === "connected") {
                setGmailMessage("Gmail connected successfully.");
                syncGmailStatus();
            } else if (gmailParam === "error") {
                setGmailError("Gmail OAuth failed. Please try again.");
            }
        }
    }, [searchParams]);

    useEffect(() => {
        const slackIntegration = integrations.find((i) => i.type === "slack");
        if (!slackIntegration) return;
        updateIntegration(slackIntegration.id, {
            config: {
                ...(slackIntegration.config ?? {}),
                channels: selectedSlackChannels,
            },
        });
    }, [selectedSlackChannels]);

    const connectSlack = async () => {
        setSlackError(null);
        try {
            const authUrl = await getSlackOAuthUrl();
            window.location.href = authUrl;
        } catch (e) {
            setSlackError(e instanceof Error ? e.message : "Failed to start Slack OAuth");
        }
    };

    const disconnectSlackWorkspace = async () => {
        setSlackError(null);
        try {
            await disconnectSlack();
            setSlackMessage("Slack disconnected.");
            await syncSlackStatus();
        } catch (e) {
            setSlackError(e instanceof Error ? e.message : "Failed to disconnect Slack");
        }
    };

    const ingestSelectedSlackChannels = async () => {
        if (!activeSessionId) {
            setSlackError("Select an active BRD session before ingesting Slack channels.");
            return;
        }
        if (selectedSlackChannels.length === 0) {
            setSlackError("Select at least one Slack channel to ingest.");
            return;
        }

        setSlackIngesting(true);
        setSlackError(null);
        try {
            const result = await ingestSlackChannels(activeSessionId, selectedSlackChannels);
            setSlackMessage(result.message);
            await loadSessionStats();
        } catch (e) {
            setSlackError(e instanceof Error ? e.message : "Slack ingestion failed");
        } finally {
            setSlackIngesting(false);
        }
    };

    const connectGmail = async () => {
        setGmailError(null);
        setGmailMessage(null);
        try {
            const authUrl = await getGmailOAuthUrl();
            const result = await openGmailAuthPopup(authUrl);
            if (result.status === "connected") {
                setGmailMessage("Gmail connected successfully.");
                await syncGmailStatus();
            } else if (result.status === "error") {
                setGmailError(result.reason || "Gmail OAuth failed. Please try again.");
            } else {
                await syncGmailStatus();
            }
        } catch (e) {
            setGmailError(e instanceof Error ? e.message : "Failed to start Gmail OAuth");
        }
    };

    const disconnectGmailAccount = async () => {
        setGmailError(null);
        try {
            await disconnectGmail();
            setGmailMessage("Gmail disconnected.");
            await syncGmailStatus();
        } catch (e) {
            setGmailError(e instanceof Error ? e.message : "Failed to disconnect Gmail");
        }
    };

    const ingestSelectedGmailEmails = async () => {
        if (!activeSessionId) {
            setGmailError("Select an active BRD session before ingesting Gmail emails.");
            return;
        }
        if (selectedGmailEmails.length === 0) {
            setGmailError("Select at least one email to ingest.");
            return;
        }

        setGmailIngesting(true);
        setGmailError(null);
        try {
            const result = await ingestGmailEmails(activeSessionId, selectedGmailEmails);
            setGmailMessage(result.message);
            await loadSessionStats();
        } catch (e) {
            setGmailError(e instanceof Error ? e.message : "Gmail ingestion failed");
        } finally {
            setGmailIngesting(false);
        }
    };

    return (
        <div className="p-4 sm:p-6 space-y-6 max-w-[1400px] pb-12">
            {/* Header / User Profile */}
            <div className="flex flex-col md:flex-row items-center md:items-start justify-between gap-6 border-b border-white/5 pb-8">
                <div className="flex flex-col md:flex-row items-center gap-6">
                    <div className="text-center md:text-left">
                        <h1 className="text-2xl font-bold text-zinc-100">{user?.name || "User Profile"}</h1>
                        <p className="text-zinc-500 text-sm mt-0.5">{user?.email}</p>
                        <div className="flex items-center gap-2 mt-3">
                            <span className="px-2 py-0.5 rounded-full bg-white/5 border border-white/10 text-zinc-400 text-[10px] font-bold uppercase tracking-wider">
                                Product Team
                            </span>
                        </div>
                    </div>
                </div>
                <button
                    onClick={() => setEditingProfile(true)}
                    className="flex items-center gap-2 px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-zinc-300 text-sm font-medium transition-all"
                >
                    <SettingsIcon size={14} />
                    Edit Profile
                </button>
            </div>

            {editingProfile && (
                <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-[100]" onClick={() => setEditingProfile(false)}>
                    <div className="glass-card border-white/10 rounded-xl p-6 w-full max-w-md shadow-2xl" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center justify-between mb-6">
                            <h3 className="text-lg font-bold text-zinc-100">Edit Profile</h3>
                            <button onClick={() => setEditingProfile(false)} className="text-zinc-500 hover:text-white transition-colors">
                                <XCircle size={20} />
                            </button>
                        </div>
                        <form
                            onSubmit={(e) => {
                                e.preventDefault();
                                const formData = new FormData(e.currentTarget);
                                const name = formData.get("name") as string;
                                const email = formData.get("email") as string;
                                updateUser(name, email);
                                setEditingProfile(false);
                            }}
                            className="space-y-4"
                        >
                            <div className="space-y-1.5">
                                <label className="block text-xs font-bold text-zinc-500 uppercase tracking-widest">Full Name</label>
                                <input
                                    type="text"
                                    name="name"
                                    required
                                    defaultValue={user?.name}
                                    className="w-full px-3 py-2 bg-zinc-950 border border-white/10 rounded-lg text-zinc-100 placeholder-zinc-700 text-sm focus:outline-none focus:ring-1 focus:ring-cyan-500/50 transition-all"
                                    placeholder="Your name"
                                />
                            </div>
                            <div className="space-y-1.5">
                                <label className="block text-xs font-bold text-zinc-500 uppercase tracking-widest">Email Address</label>
                                <input
                                    type="email"
                                    name="email"
                                    required
                                    defaultValue={user?.email}
                                    className="w-full px-3 py-2 bg-zinc-950 border border-white/10 rounded-lg text-zinc-100 placeholder-zinc-700 text-sm focus:outline-none focus:ring-1 focus:ring-cyan-500/50 transition-all"
                                    placeholder="your@email.com"
                                />
                            </div>
                            <div className="flex gap-3 pt-4">
                                <button
                                    type="button"
                                    onClick={() => setEditingProfile(false)}
                                    className="flex-1 px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-zinc-300 text-sm font-medium transition-colors"
                                >
                                    Cancel
                                </button>
                                <button type="submit" className="flex-1 px-4 py-2 bg-zinc-100 hover:bg-white text-zinc-950 rounded-lg text-sm font-bold transition-all">
                                    Save Changes
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {(slackError || slackMessage || gmailError || gmailMessage) && (
                <div
                    className={`px-4 py-2.5 rounded-xl border flex items-center gap-2 text-xs transition-all ${(slackError || gmailError) ? "border-red-500/20 bg-red-500/10 text-red-300" : "border-emerald-500/20 bg-emerald-500/10 text-emerald-300"
                        }`}
                >
                    {(slackError || gmailError) ? <XCircle size={14} /> : <CheckCircle2 size={14} />}
                    <span>{slackError ?? slackMessage ?? gmailError ?? gmailMessage}</span>
                </div>
            )}

            {/* S2-01 style Connector Cards */}
            <div>
                <div className="mb-6">
                    <h2 className="text-base font-bold text-zinc-100">Manage Connectors</h2>
                    <p className="text-xs text-zinc-500 mt-0.5">Connect and manage your data bridge connectors</p>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-xl">
                    {dataSources.map((source) => {
                        const isSlack = source.id === "slack";
                        const isGmail = source.id === "gmail";
                        const isConnected = isSlack ? Boolean(slackStatus?.connected) : isGmail ? Boolean(gmailStatus?.connected) : false;

                        return (
                            <div key={source.id} className="glass-card p-4 rounded-xl border-white/5 flex items-center justify-between gap-4 relative overflow-hidden group">
                                <div className="flex items-center gap-3">
                                    <div className={cn(
                                        "w-10 h-10 rounded-xl border flex items-center justify-center transition-colors shadow-sm flex-shrink-0",
                                        isSlack ? "bg-white border-white" : 
                                        isGmail ? "bg-white" : 
                                        "bg-white/5 border-white/10"
                                    )}>
                                        {isSlack ? <SlackLogo className="w-[22px] h-[22px]" /> : 
                                         isGmail ? <GmailLogo className="w-[22px] h-[22px]" /> : 
                                         <source.icon size={18} className="text-zinc-600" />}
                                    </div>
                                    <div>
                                        <h3 className="text-sm font-semibold text-zinc-100">{source.name}</h3>
                                        <div className="flex items-center gap-1.5 mt-0.5">
                                            <div className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-emerald-400' : 'bg-zinc-600'}`} />
                                            <span className={`text-[10px] font-bold uppercase tracking-wider ${isConnected ? 'text-emerald-400' : 'text-zinc-500'}`}>
                                                {isConnected ? 'Connected' : 'Inactive'}
                                            </span>
                                        </div>
                                    </div>
                                </div>

                                <div className="flex-shrink-0">
                                    {isConnected ? (
                                        <button
                                            onClick={isSlack ? disconnectSlackWorkspace : disconnectGmailAccount}
                                            className="px-3.5 py-1.5 rounded-lg font-bold text-xs bg-white/5 hover:bg-red-500/10 hover:text-red-400 border border-white/10 hover:border-red-500/20 text-zinc-400 transition-all uppercase tracking-wider"
                                        >
                                            Disconnect
                                        </button>
                                    ) : (
                                        <button
                                            onClick={isSlack ? connectSlack : connectGmail}
                                            className={cn(
                                                "px-3.5 py-1.5 rounded-lg font-bold text-xs transition-all uppercase tracking-wider",
                                                isSlack ? "bg-white text-zinc-950 hover:bg-zinc-200" : "bg-red-500 text-white hover:bg-red-600"
                                            )}
                                        >
                                            Connect
                                        </button>
                                    )}
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* BRD Sessions Linked to Account */}
            <div className="pt-6 border-t border-white/5">
                <div className="mb-6">
                    <h2 className="text-base font-bold text-zinc-100">Linked BRD Sessions</h2>
                    <p className="text-xs text-zinc-500 mt-0.5">Manage and activate the Business Requirement Document sessions linked to this account</p>
                </div>

                {sessions.length === 0 ? (
                    <div className="glass-card p-8 rounded-xl border-white/5 text-center bg-white/[0.01]">
                        <FileText className="mx-auto text-zinc-600 mb-3" size={32} />
                        <p className="text-sm text-zinc-400">No BRD sessions found linked to this account.</p>
                        <p className="text-xs text-zinc-500 mt-1">Go to the Dashboard to create a new session.</p>
                        <Link href="/dashboard" className="inline-block mt-4">
                            <button className="btn-primary text-xs flex items-center gap-1.5">
                                Go to Dashboard
                                <ArrowRight size={12} />
                            </button>
                        </Link>
                    </div>
                ) : (
                    <div className="space-y-3">
                        {sessions.map((sess) => {
                            const isActive = sess.id === activeSessionId;
                            return (
                                <div
                                    key={sess.id}
                                    className={cn(
                                        "glass-card p-4 rounded-xl border-white/5 flex flex-col md:flex-row md:items-center justify-between gap-4 transition-all hover:border-white/10 hover:bg-white/[0.02]",
                                        isActive && "border-cyan-500/20 bg-cyan-500/[0.02] hover:border-cyan-500/30"
                                    )}
                                >
                                    <div className="flex items-start gap-3 flex-1 min-w-0">
                                        <div className={cn(
                                            "w-10 h-10 rounded-xl border flex items-center justify-center flex-shrink-0 transition-colors",
                                            isActive ? "bg-cyan-500/10 border-cyan-500/20 text-cyan-400" : "bg-white/5 border-white/10 text-zinc-400"
                                        )}>
                                            <FileText size={18} />
                                        </div>
                                        <div className="min-w-0">
                                            <div className="flex items-center gap-2 flex-wrap">
                                                <h3 className="text-sm font-semibold text-zinc-100 truncate">{sess.name}</h3>
                                                {isActive && (
                                                    <span className="px-2 py-0.5 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 text-[9px] font-bold uppercase tracking-wider">
                                                        Active Session
                                                    </span>
                                                )}
                                                {sess.role && (
                                                    <span className={cn(
                                                        "px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wider",
                                                        sess.role === "owner" ? "bg-purple-500/10 border border-purple-500/20 text-purple-400" :
                                                        sess.role === "editor" ? "bg-blue-500/10 border border-blue-500/20 text-blue-400" :
                                                        "bg-zinc-500/10 border border-zinc-500/20 text-zinc-400"
                                                    )}>
                                                        {sess.role}
                                                    </span>
                                                )}
                                            </div>
                                            <p className="text-xs text-zinc-500 truncate mt-0.5">
                                                {sess.description || "No description provided."}
                                            </p>
                                            <div className="flex items-center gap-3 mt-1.5 text-[10px] text-zinc-600 font-mono">
                                                <span>ID: {sess.id}</span>
                                                <span>•</span>
                                                <span>Created: {new Date(sess.createdAt).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}</span>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="flex items-center gap-3 self-end md:self-auto flex-shrink-0">
                                        <div className="text-right hidden sm:block">
                                            <div className="flex items-center gap-1.5 justify-end">
                                                <span className={cn(
                                                    "w-1.5 h-1.5 rounded-full",
                                                    sess.status === "active" ? "bg-emerald-400" :
                                                    sess.status === "complete" ? "bg-cyan-400" :
                                                    "bg-zinc-500"
                                                )} />
                                                <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-400">
                                                    {sess.status}
                                                </span>
                                            </div>
                                        </div>
                                        {isActive ? (
                                            <Link href="/dashboard">
                                                <button className="flex items-center gap-1.5 px-3.5 py-1.5 bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/20 rounded-lg text-cyan-400 text-xs font-bold transition-all uppercase tracking-wider">
                                                    Open Dashboard
                                                    <ArrowRight size={12} />
                                                </button>
                                            </Link>
                                        ) : (
                                            <Link href="/dashboard">
                                                <button
                                                    onClick={() => setActive(sess.id)}
                                                    className="flex items-center gap-1.5 px-3.5 py-1.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-zinc-300 hover:text-white text-xs font-bold transition-all uppercase tracking-wider"
                                                >
                                                    Activate &amp; Open
                                                    <ArrowRight size={12} />
                                                </button>
                                            </Link>
                                        )}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>

            {/* S1-04 style Stats Row */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 pt-4 border-t border-white/5">
                <div className="glass-card p-4 rounded-xl border-white/5 text-center bg-white/[0.01]">
                    <p className="text-2xl font-bold text-zinc-100">{activeSources}</p>
                    <p className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest mt-1">Active Sources</p>
                </div>
                <div className="glass-card p-4 rounded-xl border-white/5 text-center bg-white/[0.01]">
                    <p className="text-2xl font-bold text-zinc-100">
                        {statsLoading ? <Loader2 size={16} className="animate-spin mx-auto text-zinc-700" /> : totalChunks}
                    </p>
                    <p className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest mt-1">Processed</p>
                </div>
                <div className="glass-card p-4 rounded-xl border-white/5 text-center bg-white/[0.01]">
                    <p className="text-2xl font-bold text-emerald-400">
                        {statsLoading ? <Loader2 size={16} className="animate-spin mx-auto text-emerald-900" /> : `${relevancePct}%`}
                    </p>
                    <p className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest mt-1">Relevance</p>
                </div>
                <div className="glass-card p-4 rounded-xl border-white/5 text-center bg-white/[0.01]">
                    <p className="text-2xl font-bold text-amber-500">
                        {statsLoading ? <Loader2 size={16} className="animate-spin mx-auto text-amber-900" /> : noiseChunks}
                    </p>
                    <p className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest mt-1">Metadata-only</p>
                </div>
            </div>
        </div>
    );
}
