"use client";

import { useState, useEffect, useCallback, useRef } from 'react';
import { 
    Search, Filter, ChevronDown, Mail, Inbox, Send, Star, Clock, Trash2, 
    MoreVertical, CheckSquare, Square, RefreshCw, X, Paperclip, 
    AlertCircle, Loader2, ArrowLeft, Trash, FileText, Download, Menu
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '@/lib/utils';
import { GmailLogo } from '@/components/icons/GmailLogo';
import { 
    getGmailStatus, getGmailProfile, 
    getGmailThreadFull, getGmailAttachment, getGmailOAuthUrl,
    listGmailEmails, getGmailCachedEmails, openGmailAuthPopup, type GmailEmail, type GmailSearchOptions,
    type GmailProfile, type GmailThread
} from '@/lib/apiClient';
import { getGmailCache, setGmailCache } from '@/lib/gmailCache';

interface GmailReplicaProps {
    onClose: () => void;
    onIngest: (selectedIds: string[], includeAttachments?: boolean, selectedEmails?: GmailEmail[]) => void;
    isIngesting: boolean;
}

// Friendly sandboxed iframe to prevent email HTML stylesheet pollution/bleeding
const HtmlContent = ({ html }: { html: string }) => {
    const iframeRef = useRef<HTMLIFrameElement>(null);

    useEffect(() => {
        const iframe = iframeRef.current;
        if (!iframe) return;
        
        const handleResize = () => {
            if (iframe.contentWindow?.document.body) {
                iframe.style.height = `${iframe.contentWindow.document.body.scrollHeight + 24}px`;
            }
        };
        
        iframe.addEventListener('load', handleResize);
        const timer = setTimeout(handleResize, 500);
        
        return () => {
            iframe.removeEventListener('load', handleResize);
            clearTimeout(timer);
        };
    }, [html]);

    const styledHtml = `
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                    font-size: 13.5px;
                    line-height: 1.6;
                    color: #d4d4d8; /* text-zinc-300 */
                    background-color: transparent;
                    margin: 0;
                    padding: 0;
                    word-break: break-word;
                }
                a { color: #06b6d4; text-decoration: none; }
                a:hover { text-decoration: underline; }
                img { max-width: 100%; height: auto; border-radius: 8px; }
                pre { background: rgba(255,255,255,0.05); padding: 8px; border-radius: 6px; overflow-x: auto; }
            </style>
        </head>
        <body>
            ${html}
        </body>
        </html>
    `;

    return (
        <iframe
            ref={iframeRef}
            srcDoc={styledHtml}
            sandbox="allow-popups allow-popups-to-escape-sandbox allow-same-origin"
            className="w-full border-none bg-transparent"
            style={{ height: 'auto', minHeight: '80px', display: 'block' }}
        />
    );
};

export default function GmailReplica({ onClose, onIngest, isIngesting }: GmailReplicaProps) {
    const [emails, setEmails] = useState<GmailEmail[]>([]);
    const [loading, setLoading] = useState(false);
    const [showSpinner, setShowSpinner] = useState(false);

    useEffect(() => {
        let timer: NodeJS.Timeout;
        if (loading) {
            timer = setTimeout(() => {
                setShowSpinner(true);
            }, 250);
        } else {
            setShowSpinner(false);
        }
        return () => clearTimeout(timer);
    }, [loading]);

    const [error, setError] = useState<string | null>(null);
    const [selectedIds, setSelectedIds] = useState<string[]>([]);
    const [activeFolder, setActiveFolder] = useState('INBOX');
    const [nextPageToken, setNextPageToken] = useState<string | null>(null);

    // Pagination state
    const [currentPage, setCurrentPage] = useState(1);
    const [pageTokenHistory, setPageTokenHistory] = useState<(string | null)[]>([null]); // index 0 = page 1 (no token)
    const [initialCacheLoaded, setInitialCacheLoaded] = useState(false);
    
    // Auth & Profile
    const [status, setStatus] = useState<{connected: boolean, available: boolean} | null>(null);
    const [profile, setProfile] = useState<GmailProfile | null>(null);
    
    // View state
    const [viewMode, setViewMode] = useState<'list' | 'detail'>('list');
    const [activeThread, setActiveThread] = useState<GmailThread | null>(null);
    const [threadLoading, setThreadLoading] = useState(false);

    // Search states
    const [showFilters, setShowFilters] = useState(false);
    const [searchQuery, setSearchQuery] = useState('');
    const [fromMails, setFromMails] = useState<string[]>([]);
    const [toMails, setToMails] = useState<string[]>([]);
    const [fromInput, setFromInput] = useState('');
    const [toInput, setToInput] = useState('');
    const [includeAttachments, setIncludeAttachments] = useState(true);
    const [sidebarCollapsed, setSidebarCollapsed] = useState(true);

    const fetchStatus = useCallback(async () => {
        try {
            const s = await getGmailStatus();
            setStatus(s);
            if (s.connected) {
                const cachedProfileStr = localStorage.getItem('gmail_profile');
                if (cachedProfileStr) {
                    try {
                        setProfile(JSON.parse(cachedProfileStr));
                    } catch (e) {
                        const p = await getGmailProfile();
                        setProfile(p);
                        localStorage.setItem('gmail_profile', JSON.stringify(p));
                    }
                } else {
                    const p = await getGmailProfile();
                    setProfile(p);
                    localStorage.setItem('gmail_profile', JSON.stringify(p));
                }
            } else {
                localStorage.removeItem('gmail_profile');
                setProfile(null);
            }
        } catch (e) {
            console.error("Failed to fetch Gmail status:", e);
        }
    }, []);

    const PAGE_SIZE = 20;

    const fetchEmails = useCallback(async (options: GmailSearchOptions & { forceRefresh?: boolean } = {}) => {
        setLoading(true);
        setError(null);
        try {
            let qParts = [];
            
            if (options.q !== undefined) {
                if (options.q) qParts.push(options.q);
            } else if (searchQuery) {
                qParts.push(searchQuery);
            }

            const finalFrom = options.from !== undefined ? options.from : (fromMails.length > 0 ? (fromMails.length === 1 ? fromMails[0] : `(${fromMails.join(' OR ')})`) : '');
            const finalTo = options.to !== undefined ? options.to : (toMails.length > 0 ? (toMails.length === 1 ? toMails[0] : `(${toMails.join(' OR ')})`) : '');
            
            if (finalFrom) qParts.push(`from:${finalFrom}`);
            if (finalTo) qParts.push(`to:${finalTo}`);
            
            const queryIsGlobal = !!(finalFrom || finalTo);

            if (!queryIsGlobal && activeFolder !== 'INBOX') {
                qParts.push(`label:${activeFolder}`);
            }

            const cacheKey = qParts.length > 0 ? qParts.join(' ') : `folder:${activeFolder}`;

            // Check frontend cache for page 1 (no pageToken, no forceRefresh)
            if (!options.pageToken && !options.forceRefresh) {
                const cached = getGmailCache(cacheKey);
                if (cached) {
                    setEmails(cached.emails);
                    setNextPageToken(cached.nextPageToken);
                    setLoading(false);
                    return;
                }
            }

            const res = await listGmailEmails({ 
                count: PAGE_SIZE, 
                ...options,
                bypassCache: options.bypassCache || options.forceRefresh,
                q: qParts.length > 0 ? qParts.join(' ') : undefined
            });

            setEmails(res.emails);
            setNextPageToken(res.next_page_token || null);

            // Cache page 1 results (no pageToken means first page)
            if (!options.pageToken) {
                setGmailCache(cacheKey, {
                    emails: res.emails,
                    nextPageToken: res.next_page_token || null
                });
            }
        } catch (e: any) {
            if (e.status === 401) {
                setStatus(prev => prev ? { ...prev, connected: false } : null);
            }
            setError(e instanceof Error ? e.message : 'Failed to load emails');
        } finally {
            setLoading(false);
        }
    }, [searchQuery, activeFolder, fromMails, toMails]);

    // Navigate to next page
    const goNextPage = useCallback(() => {
        if (!nextPageToken) return;
        // Save current token to history so we can go back
        setPageTokenHistory(prev => {
            const updated = [...prev];
            // Ensure we have a slot for the next page
            if (updated.length <= currentPage) {
                updated.push(nextPageToken);
            } else {
                updated[currentPage] = nextPageToken;
            }
            return updated;
        });
        setCurrentPage(prev => prev + 1);
        fetchEmails({ pageToken: nextPageToken });
    }, [nextPageToken, currentPage, fetchEmails]);

    // Navigate to previous page
    const goPrevPage = useCallback(() => {
        if (currentPage <= 1) return;
        const prevPage = currentPage - 1;
        const prevToken = pageTokenHistory[prevPage - 1] || undefined; // page 1 has no token
        setCurrentPage(prevPage);
        if (prevToken) {
            fetchEmails({ pageToken: prevToken });
        } else {
            // Page 1 — fetch without token
            fetchEmails({});
        }
    }, [currentPage, pageTokenHistory, fetchEmails]);

    // Reset pagination when folder/search changes
    const resetPagination = useCallback(() => {
        setCurrentPage(1);
        setPageTokenHistory([null]);
    }, []);

    // Removed debounced search as requested by user.
    // Search now only triggers via explicit submit (pressing the search icon).

    useEffect(() => {
        fetchStatus();
    }, [fetchStatus]);

    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') {
                onClose();
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [onClose]);

    // On connect: load cached emails instantly, then full page
    useEffect(() => {
        if (!status?.connected) return;
        if (initialCacheLoaded) {
            // Already loaded cache once, just do a normal fetch on folder change
            resetPagination();
            fetchEmails();
            return;
        }
        // First load: try backend cache for instant display
        setInitialCacheLoaded(true);
        (async () => {
            // 1. Show cached emails instantly
            const cached = await getGmailCachedEmails();
            if (cached.cached && cached.emails.length > 0) {
                setEmails(cached.emails);
                setNextPageToken(cached.next_page_token || null);
            }
            // 2. Fetch full page (20 emails) in parallel
            fetchEmails({ forceRefresh: true });
        })();
    }, [status?.connected, activeFolder]); // activeFolder change triggers

    const handleSearch = (e?: React.FormEvent) => {
        e?.preventDefault();
        resetPagination();
        fetchEmails({ forceRefresh: true });
    };

    const toggleSelection = (id: string) => {
        setSelectedIds(prev => 
            prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
        );
    };

    const toggleSelectAll = () => {
        if (selectedIds.length === emails.length) {
            setSelectedIds([]);
        } else {
            setSelectedIds(emails.map(e => e.message_id));
        }
    };

    const systemFolders = [
        { id: 'INBOX', label: 'Inbox', icon: Inbox, color: 'text-blue-400' },
        { id: 'STARRED', label: 'Starred', icon: Star, color: 'text-yellow-400' },
        { id: 'SENT', label: 'Sent', icon: Send, color: 'text-emerald-400' },
        { id: 'DRAFTS', label: 'Drafts', icon: Paperclip, color: 'text-zinc-400' },
        { id: 'SPAM', label: 'Spam', icon: AlertCircle, color: 'text-orange-400' },
        { id: 'TRASH', label: 'Trash', icon: Trash, color: 'text-red-400' },
    ];

    const openThread = async (id: string) => {
        setThreadLoading(true);
        setViewMode('detail');
        try {
            const thread = await getGmailThreadFull(id);
            setActiveThread(thread);
        } catch (e: any) {
            if (e.status === 401) {
                setStatus(prev => prev ? { ...prev, connected: false } : null);
                setViewMode('list');
            }
            setError("Failed to load thread details.");
        } finally {
            setThreadLoading(false);
        }
    };

    const handleConnect = async () => {
        try {
            const url = await getGmailOAuthUrl();
            const result = await openGmailAuthPopup(url);
            if (result.status === "connected") {
                await fetchStatus();
            } else if (result.status === "error") {
                setError(result.reason || "Gmail OAuth failed. Please try again.");
            } else {
                await fetchStatus();
            }
        } catch (e) {
            setError(e instanceof Error ? e.message : "Failed to start Gmail OAuth");
        }
    };

    const parseMessageBody = (payload: any) => {
        const getPart = (parts: any[]): any => {
            let body = parts.find(p => p.mimeType === 'text/html');
            if (!body) body = parts.find(p => p.mimeType === 'text/plain');
            if (!body) {
                for (const part of parts) {
                    if (part.parts) {
                        const found = getPart(part.parts);
                        if (found) return found;
                    }
                }
            }
            return body;
        };

        let part = payload.parts ? getPart(payload.parts) : payload;
        if (part?.body?.data) {
            try {
                return atob(part.body.data.replace(/-/g, '+').replace(/_/g, '/'));
            } catch (e) {
                return part.body.data;
            }
        }
        return payload.snippet || "";
    };

    const getAttachments = (payload: any): any[] => {
        const list: any[] = [];
        const walk = (p: any) => {
            if (p.filename && p.body?.attachmentId) {
                list.push({
                    id: p.body.attachmentId,
                    filename: p.filename,
                    mimeType: p.mimeType,
                    size: p.body.size,
                    messageId: payload.messageId || ""
                });
            }
            if (p.parts) p.parts.forEach(walk);
        };
        walk(payload);
        return list;
    };

    const downloadAttachment = async (msgId: string, attId: string, filename: string) => {
        try {
            const res = await getGmailAttachment(msgId, attId);
            const blob = new Blob([Uint8Array.from(atob(res.data.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0))], { type: 'application/octet-stream' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            a.click();
        } catch (e) {
            setError("Failed to download attachment.");
        }
    };

    return (
        <motion.div 
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="fixed inset-4 sm:inset-10 z-50 flex flex-col glass-card border-white/10 rounded-2xl shadow-2xl overflow-hidden"
            style={{ backdropFilter: 'blur(30px) saturate(180%)' }}
        >
            {/* Header / Search Bar Area */}
            <div className="flex items-center gap-4 px-6 py-4 border-b border-white/5 bg-white/5">
                <div className="flex items-center gap-2">
                    <button onClick={onClose} className="p-2 hover:bg-white/10 rounded-full text-zinc-400 transition-colors" title="Close">
                        <X size={20} />
                    </button>
                </div>
                
                <div className="flex-1 flex items-center gap-3">
                    {/* Increased search bar size */}
                    <div className="w-96 relative flex items-center">
                        <form onSubmit={handleSearch} className="flex-1 flex items-center bg-black/40 border border-white/10 rounded-xl px-4 py-2 hover:border-white/20 focus-within:border-cyan-500/50 focus-within:bg-black/60 transition-all">
                            <Search size={18} className="text-zinc-500 mr-3" />
                            <input 
                                type="text" 
                                placeholder="Search mail..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                className="bg-transparent border-none focus:outline-none text-sm text-zinc-100 w-full placeholder-zinc-600"
                            />
                            {searchQuery && (
                                <button
                                    type="button"
                                    onClick={() => setSearchQuery('')}
                                    className="p-1 hover:bg-white/10 rounded-full text-zinc-400 hover:text-zinc-200 transition-colors ml-2"
                                >
                                    <X size={14} />
                                </button>
                            )}
                        </form>
                    </div>

                    {/* Bigger from and to forms */}
                    <form onSubmit={handleSearch} className="flex-1 flex items-center gap-2">
                        {/* FROM Input Box */}
                        <div className="flex-1 flex items-center flex-wrap bg-black/40 border border-white/10 rounded-xl px-3 py-1.5 gap-1.5 focus-within:border-cyan-500/50 hover:border-white/20 transition-all min-h-[38px]">
                            <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest border-r border-white/10 pr-2 mr-1">From</span>
                            <div className="flex flex-wrap gap-1.5 items-center flex-1">
                                {fromMails.map((mail, idx) => (
                                    <span key={idx} className="flex items-center gap-1.5 bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 px-2.5 py-1 rounded-md text-[11px] font-mono">
                                        {mail}
                                        <button 
                                            type="button" 
                                            onClick={() => setFromMails(prev => prev.filter((_, i) => i !== idx))}
                                            className="hover:bg-cyan-500/20 rounded-full p-0.5 transition-colors"
                                        >
                                            <X size={10} />
                                        </button>
                                    </span>
                                ))}
                                <input 
                                    type="text" 
                                    value={fromInput} 
                                    onChange={e => setFromInput(e.target.value)}
                                    onKeyDown={e => {
                                        if (e.key === 'Enter' || e.key === ',' || e.key === ' ') {
                                            e.preventDefault();
                                            const val = fromInput.trim().replace(/,$/, '');
                                            if (val) {
                                                if (!fromMails.includes(val)) {
                                                    setFromMails(prev => [...prev, val]);
                                                }
                                                setFromInput('');
                                            } else if (e.key === 'Enter') {
                                                handleSearch();
                                            }
                                        } else if (e.key === 'Backspace' && !fromInput && fromMails.length > 0) {
                                            setFromMails(prev => prev.slice(0, -1));
                                        }
                                    }}
                                    onBlur={() => {
                                        const val = fromInput.trim();
                                        if (val) {
                                            if (!fromMails.includes(val)) {
                                                setFromMails(prev => [...prev, val]);
                                            }
                                            setFromInput('');
                                        }
                                    }}
                                    placeholder={fromMails.length === 0 ? "user@gmail.com" : ""}
                                    className="bg-transparent border-none focus:outline-none text-[11px] text-zinc-100 min-w-[80px] flex-1 placeholder-zinc-700 font-mono"
                                />
                            </div>
                        </div>

                        {/* TO Input Box */}
                        <div className="flex-1 flex items-center flex-wrap bg-black/40 border border-white/10 rounded-xl px-3 py-1.5 gap-1.5 focus-within:border-cyan-500/50 hover:border-white/20 transition-all min-h-[38px]">
                            <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest border-r border-white/10 pr-2 mr-1">To</span>
                            <div className="flex flex-wrap gap-1.5 items-center flex-1">
                                {toMails.map((mail, idx) => (
                                    <span key={idx} className="flex items-center gap-1.5 bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 px-2.5 py-1 rounded-md text-[11px] font-mono">
                                        {mail}
                                        <button 
                                            type="button" 
                                            onClick={() => setToMails(prev => prev.filter((_, i) => i !== idx))}
                                            className="hover:bg-cyan-500/20 rounded-full p-0.5 transition-colors"
                                        >
                                            <X size={10} />
                                        </button>
                                    </span>
                                ))}
                                <input 
                                    type="text" 
                                    value={toInput} 
                                    onChange={e => setToInput(e.target.value)}
                                    onKeyDown={e => {
                                        if (e.key === 'Enter' || e.key === ',' || e.key === ' ') {
                                            e.preventDefault();
                                            const val = toInput.trim().replace(/,$/, '');
                                            if (val) {
                                                if (!toMails.includes(val)) {
                                                    setToMails(prev => [...prev, val]);
                                                }
                                                setToInput('');
                                            } else if (e.key === 'Enter') {
                                                handleSearch();
                                            }
                                        } else if (e.key === 'Backspace' && !toInput && toMails.length > 0) {
                                            setToMails(prev => prev.slice(0, -1));
                                        }
                                    }}
                                    onBlur={() => {
                                        const val = toInput.trim();
                                        if (val) {
                                            if (!toMails.includes(val)) {
                                                setToMails(prev => [...prev, val]);
                                            }
                                            setToInput('');
                                        }
                                    }}
                                    placeholder={toMails.length === 0 ? "recipient" : ""}
                                    className="bg-transparent border-none focus:outline-none text-[11px] text-zinc-100 min-w-[80px] flex-1 placeholder-zinc-700 font-mono"
                                />
                            </div>
                        </div>

                        <button type="submit" title="Search Users" className="p-2.5 bg-cyan-500/10 hover:bg-cyan-500/30 border border-cyan-500/20 rounded-lg text-cyan-400 transition-all flex items-center justify-center self-stretch">
                            <Search size={16} />
                        </button>
                    </form>
                </div>

                <div className="flex items-center gap-3 ml-4">
                    <button 
                        onClick={() => status?.connected ? fetchEmails({ forceRefresh: true }) : fetchStatus()} 
                        disabled={loading}
                        className="p-2 hover:bg-white/10 rounded-full text-zinc-400 transition-colors disabled:opacity-30"
                        title="Sync Emails"
                    >
                        <RefreshCw size={18} className={cn(loading && "animate-spin")} />
                    </button>
                </div>
            </div>

            <div className="flex-1 flex overflow-hidden relative">
                {/* Connection Overlay */}
                <AnimatePresence>
                    {status && !status.connected && (
                        <motion.div 
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            className="absolute inset-0 z-40 bg-black/60 backdrop-blur-md flex flex-col items-center justify-center p-6 text-center"
                        >
                            <div className="w-20 h-20 bg-white rounded-2xl flex items-center justify-center mx-auto mb-6 shadow-xl">
                                <GmailLogo className="w-10 h-10" />
                            </div>
                            <h2 className="text-xl font-bold text-zinc-100 mb-2">Connect your Gmail</h2>
                            <p className="text-sm text-zinc-400 max-w-xs mb-8">
                                Beacon needs read-only access to your emails to extract requirements and decisions for your BRDs.
                            </p>
                            <button 
                                onClick={handleConnect}
                                className="px-8 py-3 bg-white text-zinc-950 font-black rounded-2xl flex items-center gap-3 hover:scale-105 transition-all shadow-xl shadow-white/10"
                            >
                                <img src="https://www.google.com/favicon.ico" className="w-4 h-4" alt="Google" />
                                Sign in with Google
                            </button>
                        </motion.div>
                    )}
                </AnimatePresence>
                {/* Sidebar */}
                <motion.div 
                    animate={{ width: sidebarCollapsed ? 64 : 260 }}
                    transition={{ type: "spring", stiffness: 300, damping: 30 }}
                    className="border-r border-white/5 flex flex-col overflow-hidden relative group/sidebar bg-black/20"
                >
                    <div className="p-4 flex items-center">
                        <button 
                            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
                            className="p-2 hover:bg-white/10 rounded-xl text-zinc-400 transition-colors"
                            title={sidebarCollapsed ? "Expand Sidebar" : "Collapse Sidebar"}
                        >
                            <Menu size={22} />
                        </button>
                    </div>

                    <div className="flex-1 space-y-1 px-3 mt-2 overflow-y-auto custom-scrollbar pb-10">
                        {systemFolders.map(folder => {
                            const isActive = activeFolder === folder.id;
                            return (
                                <button 
                                    key={folder.id}
                                    onClick={() => { setActiveFolder(folder.id); setViewMode('list'); setSearchQuery(''); resetPagination(); }}
                                    className={cn(
                                        "w-full flex items-center gap-4 px-3 py-2 rounded-lg transition-all border",
                                        isActive 
                                            ? "bg-cyan-500/10 text-cyan-400 font-bold border-cyan-500/20" 
                                            : "text-zinc-500 hover:bg-white/5 hover:text-zinc-300 border-transparent"
                                    )}
                                >
                                    <div className="flex-shrink-0">
                                        <folder.icon size={18} className={isActive ? folder.color : "text-zinc-500"} />
                                    </div>
                                    {!sidebarCollapsed && <span className="text-xs truncate">{folder.label}</span>}
                                </button>
                            );
                        })}


                    </div>

                    {/* Bottom Profile Area */}
                    <div className="p-4 border-t border-white/5 bg-black/40 flex items-center gap-3 mt-auto">
                        {profile ? (
                            <>
                                <img 
                                    src={profile.picture} 
                                    alt={profile.name} 
                                    className={cn("rounded-full border border-white/10 flex-shrink-0 transition-all", sidebarCollapsed ? "w-8 h-8" : "w-10 h-10")} 
                                />
                                {!sidebarCollapsed && (
                                    <div className="flex flex-col min-w-0">
                                        <span className="text-xs font-bold text-zinc-200 leading-none truncate">{profile.name}</span>
                                        <span className="text-[10px] text-zinc-500 leading-none mt-1.5 truncate">{profile.email}</span>
                                    </div>
                                )}
                            </>
                        ) : (
                            <>
                                <div className={cn("bg-white shadow-sm flex items-center justify-center flex-shrink-0 transition-all rounded-xl", sidebarCollapsed ? "w-8 h-8" : "w-10 h-10")}>
                                    <GmailLogo className={sidebarCollapsed ? "w-[16px] h-[16px]" : "w-[20px] h-[20px]"} />
                                </div>
                                {!sidebarCollapsed && (
                                    <div className="flex flex-col">
                                        <span className="text-xs font-bold text-zinc-200 leading-none">Gmail disconnected</span>
                                    </div>
                                )}
                            </>
                        )}
                    </div>
                </motion.div>

                {/* Main Content Area */}
                <div className="flex-1 flex flex-col min-w-0 bg-black/20">
                    <div className="px-6 py-3 border-b border-white/5 flex items-center justify-between">
                        <div className="flex items-center gap-2 text-xs text-zinc-500 font-mono">
                            <span className="mr-2">
                                {emails.length > 0
                                    ? `${(currentPage - 1) * PAGE_SIZE + 1} – ${(currentPage - 1) * PAGE_SIZE + emails.length}`
                                    : 'No emails'}
                            </span>
                            <span className="text-zinc-700">Page {currentPage}</span>
                            <div className="flex items-center gap-1 border-l border-white/10 pl-3">
                                <button 
                                    onClick={goPrevPage}
                                    disabled={currentPage <= 1}
                                    className="p-1.5 hover:bg-white/10 rounded-lg text-zinc-500 transition-colors disabled:opacity-30"
                                    title="Previous Page"
                                >
                                    <motion.div whileHover={{ x: -2 }}><ChevronDown size={16} className="rotate-90" /></motion.div>
                                </button>
                                <button 
                                    onClick={goNextPage}
                                    disabled={!nextPageToken}
                                    className="p-1.5 hover:bg-white/10 rounded-lg text-zinc-500 transition-colors disabled:opacity-30"
                                    title="Next Page"
                                >
                                    <motion.div whileHover={{ x: 2 }}><ChevronDown size={16} className="-rotate-90" /></motion.div>
                                </button>
                            </div>
                        </div>
                    </div>

                    <div className="flex-1 overflow-y-auto custom-scrollbar relative">
                        <AnimatePresence mode="wait">
                            {viewMode === 'detail' ? (
                                <motion.div 
                                    key="detail"
                                    initial={{ opacity: 0, x: 20 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    exit={{ opacity: 0, x: -20 }}
                                    className="absolute inset-0 bg-black flex flex-col"
                                >
                                    <div className="flex items-center gap-4 px-6 py-4 border-b border-white/5 sticky top-0 bg-black z-10">
                                        <button onClick={() => setViewMode('list')} className="p-2 hover:bg-white/10 rounded-full text-zinc-400">
                                            <ArrowLeft size={18} />
                                        </button>
                                        <div className="flex-1 min-w-0">
                                            <h2 className="text-zinc-100 font-bold truncate">{activeThread?.messages[0]?.payload.headers.find((h: any) => h.name === 'Subject')?.value || '(No Subject)'}</h2>
                                        </div>
                                    </div>
                                    
                                    <div className="flex-1 overflow-y-auto p-6 space-y-8">
                                        {threadLoading ? (
                                            <div className="h-full flex flex-col items-center justify-center py-20">
                                                <Loader2 size={30} className="text-cyan-400 animate-spin" />
                                            </div>
                                        ) : activeThread?.messages.map((msg, idx) => (
                                            <div key={msg.id} className="space-y-4">
                                                <div className="flex items-start justify-between">
                                                    <div className="flex items-center gap-3">
                                                        <div className="w-8 h-8 rounded-full bg-zinc-800 flex items-center justify-center text-[10px] font-bold text-zinc-400">
                                                            {msg.payload.headers.find((h: any) => h.name === 'From')?.value[0].toUpperCase()}
                                                        </div>
                                                                                        <div>
                                                            <p className="text-sm font-bold text-zinc-100">{msg.payload.headers.find((h: any) => h.name === 'From')?.value}</p>
                                                            <div className="flex items-center gap-2 flex-wrap mt-1">
                                                                <p className="text-[10px] text-zinc-500">To: {msg.payload.headers.find((h: any) => h.name === 'To')?.value}</p>
                                                                {msg.labelIds && msg.labelIds.map(label => (
                                                                    <span key={label} className="bg-white/5 border border-white/10 text-cyan-400/90 px-1.5 py-0.5 rounded text-[8px] font-bold uppercase tracking-wider font-mono">
                                                                        {label}
                                                                    </span>
                                                                ))}
                                                            </div>
                                                        </div>
                                                    </div>
                                                    <span className="text-[10px] text-zinc-600 font-mono">
                                                        {(() => {
                                                            const dateHeader = msg.payload.headers.find((h: any) => h.name === 'Date')?.value;
                                                            if (!dateHeader) return 'Unknown Date';
                                                            const parsed = Date.parse(dateHeader);
                                                            return isNaN(parsed) ? dateHeader : new Date(parsed).toLocaleString();
                                                        })()}
                                                    </span>
                                                </div>
                                                <div className="text-sm text-zinc-300 leading-relaxed pl-11">
                                                    <HtmlContent html={parseMessageBody(msg.payload)} />
                                                </div>

                                                {getAttachments(msg.payload).length > 0 && (
                                                    <div className="pl-11 pt-4 flex flex-wrap gap-3">
                                                        {getAttachments(msg.payload).map(att => (
                                                            <button 
                                                                key={att.id}
                                                                onClick={() => downloadAttachment(msg.id, att.id, att.filename)}
                                                                className="flex items-center gap-3 px-4 py-2 bg-white/5 border border-white/10 rounded-xl hover:bg-white/10 transition-all group"
                                                            >
                                                                <FileText size={16} className="text-zinc-500 group-hover:text-cyan-400" />
                                                                <div className="text-left">
                                                                    <p className="text-[11px] font-bold text-zinc-300 truncate max-w-[120px]">{att.filename}</p>
                                                                    <p className="text-[9px] text-zinc-500">{(att.size / 1024).toFixed(1)} KB</p>
                                                                </div>
                                                                <Download size={14} className="ml-2 text-zinc-600 opacity-0 group-hover:opacity-100 transition-opacity" />
                                                            </button>
                                                        ))}
                                                    </div>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                </motion.div>
                            ) : loading ? (
                                showSpinner ? (
                                    <div key="loading" className="h-full flex flex-col items-center justify-center text-zinc-600 animate-in fade-in duration-500">
                                        <Loader2 size={40} className="animate-spin mb-4 opacity-20" />
                                        <p className="text-xs font-mono uppercase tracking-[0.2em]">Synchronizing Emails...</p>
                                    </div>
                                ) : (
                                    <div key="preloading" className="h-full" />
                                )
                            ) : error ? (
                                <div key="error" className="h-full flex flex-col items-center justify-center p-10 text-center">
                                    <div className="w-16 h-16 rounded-3xl bg-red-500/10 border border-red-500/20 flex items-center justify-center mb-6">
                                        <X size={32} className="text-red-400" />
                                    </div>
                                    <h3 className="text-zinc-200 font-bold mb-2">Sync Error</h3>
                                    <p className="text-sm text-zinc-500 max-w-xs">{error}</p>
                                    <button 
                                        onClick={() => fetchEmails()} 
                                        className="mt-6 px-6 py-2 bg-white/5 border border-white/10 rounded-xl text-zinc-300 text-xs font-bold hover:bg-white/10 transition-all"
                                    >
                                        Try Again
                                    </button>
                                </div>
                            ) : emails.length === 0 ? (
                                <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
                                    <GmailLogo className="w-[60px] h-[60px] mb-6 grayscale opacity-40" />
                                    <p className="text-sm text-zinc-500 font-medium">No emails found matching your criteria</p>
                                </div>
                            ) : (
                                <div key="list" className="divide-y divide-white/5 pb-28">
                                    {emails.map((email) => (
                                        <motion.div 
                                            key={email.message_id}
                                            layout
                                            initial={{ opacity: 0 }}
                                            animate={{ opacity: 1 }}
                                            className={cn(
                                                "group flex items-center gap-4 px-6 py-3 transition-colors cursor-pointer",
                                                selectedIds.includes(email.message_id) ? "bg-cyan-500/5 shadow-[inset_4px_0_0_0_rgb(6,182,212)]" : "hover:bg-white/[0.03]"
                                            )}
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                openThread(email.thread_id || email.message_id);
                                            }}
                                        >
                                            <div className="flex-shrink-0 flex items-center gap-4" onClick={(e) => e.stopPropagation()}>
                                                <div 
                                                    onClick={(e) => { e.stopPropagation(); toggleSelection(email.message_id); }}
                                                    className={cn("transition-colors", selectedIds.includes(email.message_id) ? "text-cyan-400" : "text-zinc-700 group-hover:text-zinc-500")}
                                                >
                                                    {selectedIds.includes(email.message_id) ? <CheckSquare size={18} /> : <Square size={18} />}
                                                </div>
                                                <Star size={18} className="text-zinc-800 hover:text-yellow-500 transition-colors" />
                                            </div>

                                            <div className="flex-1 min-w-0 flex items-baseline gap-6">
                                                <div className="w-48 flex-shrink-0">
                                                    <p className={cn("text-sm truncate", selectedIds.includes(email.message_id) ? "text-zinc-100 font-bold" : "text-zinc-300 group-hover:text-zinc-100")}>
                                                        {email.from.split('<')[0].trim() || email.from}
                                                    </p>
                                                </div>
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-2">
                                                        <p className={cn("text-sm truncate", !selectedIds.includes(email.message_id) && "text-zinc-100 font-medium")}>
                                                            {email.subject || '(No Subject)'}
                                                        </p>
                                                        {email.attachments?.length > 0 && <Paperclip size={12} className="text-zinc-600 flex-shrink-0" />}
                                                    </div>
                                                    <p className="text-xs text-zinc-600 truncate mt-0.5 line-clamp-1">
                                                        {email.snippet}
                                                    </p>
                                                </div>
                                            </div>

                                            <div className="w-20 text-right flex-shrink-0">
                                                <p className="text-[10px] text-zinc-600 font-mono truncate">Recent</p>
                                            </div>
                                        </motion.div>
                                    ))}
                                    

                                </div>
                            )}
                        </AnimatePresence>
                    </div>
                </div>
            </div>

            {/* Bottom Ingestion Action Bar */}
            <AnimatePresence>
                {selectedIds.length > 0 && (
                    <motion.div 
                        initial={{ y: 100 }}
                        animate={{ y: 0 }}
                        exit={{ y: 100 }}
                        className="absolute bottom-6 left-1/2 -translate-x-1/2 flex items-center gap-4 px-6 py-4 glass-card border-cyan-500/30 bg-cyan-950/20 shadow-2xl z-30"
                        style={{ backdropFilter: 'blur(20px)' }}
                    >
                        <div className="flex flex-col border-r border-white/10 pr-4">
                            <span className="text-cyan-400 font-bold text-sm">{selectedIds.length} emails selected</span>
                            <span className="text-[10px] text-zinc-500 font-medium uppercase tracking-widest">Ready for ingestion</span>
                        </div>
                        
                        <label className="flex items-center gap-2 cursor-pointer group px-2">
                            <div 
                                onClick={() => setIncludeAttachments(!includeAttachments)}
                                className={cn("w-4 h-4 rounded border transition-all flex items-center justify-center", includeAttachments ? "bg-cyan-500 border-cyan-500" : "border-white/20 group-hover:border-white/40")}
                            >
                                {includeAttachments && <CheckSquare size={12} className="text-zinc-950" />}
                            </div>
                            <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest group-hover:text-zinc-200 transition-colors">Include Attachments</span>
                        </label>

                        <div className="w-px h-8 bg-white/10 mx-2" />
                        <button 
                            onClick={() => onIngest(selectedIds, includeAttachments, emails.filter(e => selectedIds.includes(e.message_id)))}
                            disabled={isIngesting}
                            className="bg-cyan-500 hover:bg-cyan-400 text-zinc-950 font-black px-8 py-2.5 rounded-xl text-xs uppercase tracking-widest transition-all shadow-[0_0_20px_rgba(6,182,212,0.4)] disabled:opacity-50 flex items-center gap-2"
                        >
                            {isIngesting ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                            {isIngesting ? 'Ingesting...' : 'Ingest Selected'}
                        </button>
                    </motion.div>
                )}
            </AnimatePresence>
        </motion.div>
    );
}
