"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Download, Loader2, Lock, Save, Sparkles } from "lucide-react";
import { useBRDStore } from "@/store/useBRDStore";
import { exportBRD } from "@/lib/apiClient";

export default function BRDEditor({ projectId }: { projectId: string }) {
    const {
        sections,
        flags,
        loading,
        generating,
        error,
        loadBRD,
        updateSection,
        generateAll,
    } = useBRDStore();

    const [activeSectionId, setActiveSectionId] = useState<string>("executive_summary");
    const [draft, setDraft] = useState("");
    const [saving, setSaving] = useState(false);
    const [exporting, setExporting] = useState(false);

    useEffect(() => {
        if (!projectId) {
            return;
        }
        loadBRD(projectId);
    }, [projectId, loadBRD]);

    const activeSection = useMemo(
        () => sections.find((s) => s.id === activeSectionId) ?? sections[0],
        [sections, activeSectionId]
    );

    useEffect(() => {
        setDraft(activeSection?.content ?? "");
        if (!activeSection && sections.length > 0) {
            setActiveSectionId(sections[0].id);
        }
    }, [activeSection?.id, activeSection?.content, sections]);

    const sectionFlags = useMemo(
        () => flags.filter((f) => f.section_name === activeSection?.id),
        [flags, activeSection?.id]
    );

    const globalFlags = useMemo(
        () => flags.filter((f) => f.section_name === "cross_section"),
        [flags]
    );

    const handleSave = async () => {
        if (!activeSection || !projectId) {
            return;
        }
        setSaving(true);
        await updateSection(projectId, activeSection.id, draft);
        setSaving(false);
    };

    const handleExport = async () => {
        if (!projectId) {
            return;
        }
        setExporting(true);
        try {
            await exportBRD(projectId, "docx");
        } finally {
            setExporting(false);
        }
    };

    return (
        <div className="grid grid-cols-12 gap-6">
            <div className="col-span-3 bg-zinc-900/50 border border-white/5 rounded-xl p-4 h-[700px] overflow-y-auto">
                <h3 className="font-semibold text-zinc-100 mb-4">Document Outline</h3>
                <div className="space-y-1">
                    {sections.map((section) => (
                        <button
                            key={section.id}
                            onClick={() => setActiveSectionId(section.id)}
                            className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${activeSectionId === section.id
                                ? "bg-cyan-500/10 text-cyan-400 border-l-2 border-cyan-500"
                                : "text-zinc-400 hover:text-zinc-100 hover:bg-white/5"
                                }`}
                        >
                            <div className="flex items-center gap-2">
                                <span className="flex-1 truncate">{section.title}</span>
                                {section.humanEdited && <Lock size={11} className="text-yellow-400" />}
                            </div>
                        </button>
                    ))}
                </div>
            </div>

            <div className="col-span-6 space-y-4">
                <div className="flex items-center justify-between">
                    <h3 className="text-lg font-semibold text-zinc-100">{activeSection?.title ?? "BRD Section"}</h3>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={() => generateAll(projectId)}
                            disabled={generating || !projectId}
                            className="flex items-center gap-2 px-3 py-1.5 bg-purple-500/10 hover:bg-purple-500/20 border border-purple-500/20 text-purple-400 rounded-lg text-sm transition-colors disabled:opacity-50"
                        >
                            {generating ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                            {generating ? "Generating..." : "Generate BRD"}
                        </button>
                        <button
                            onClick={handleSave}
                            disabled={saving || loading || !activeSection}
                            className="flex items-center gap-2 px-3 py-1.5 bg-cyan-500 hover:bg-cyan-600 text-white rounded-lg text-sm transition-colors disabled:opacity-50"
                        >
                            {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                            Save
                        </button>
                        <button
                            onClick={handleExport}
                            disabled={exporting || !projectId}
                            className="flex items-center gap-2 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 rounded-lg text-sm transition-colors disabled:opacity-50"
                        >
                            {exporting ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                            Export DOCX
                        </button>
                    </div>
                </div>

                {error && (
                    <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
                        <AlertTriangle size={14} />
                        {error}
                    </div>
                )}

                <textarea
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    placeholder={activeSection ? `Edit ${activeSection.title}...` : "Generate BRD first"}
                    className="w-full h-[620px] bg-zinc-900/50 border border-white/5 rounded-xl p-6 text-zinc-100 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-cyan-500 font-sans resize-none"
                />
            </div>

            <div className="col-span-3 space-y-4">
                <div className="bg-zinc-900/50 border border-white/5 rounded-xl p-4 h-[700px] overflow-y-auto">
                    <h4 className="text-sm font-semibold text-zinc-100 mb-3">Validation Flags</h4>
                    {sectionFlags.length === 0 && globalFlags.length === 0 ? (
                        <p className="text-xs text-zinc-500">No validation flags for this section.</p>
                    ) : (
                        <div className="space-y-2">
                            {[...sectionFlags, ...globalFlags].map((flag, index) => (
                                <div
                                    key={`${flag.section_name}-${index}`}
                                    className="p-3 bg-zinc-950/50 rounded-lg border border-white/5"
                                >
                                    <div className="flex items-center justify-between gap-2">
                                        <span className="text-[10px] text-zinc-500 uppercase">{flag.flag_type}</span>
                                        <span className="text-[10px] text-red-300 uppercase">{flag.severity}</span>
                                    </div>
                                    <p className="text-xs text-zinc-300 mt-1">{flag.description}</p>
                                </div>
                            ))}
                        </div>
                    )}

                    <div className="mt-6 pt-4 border-t border-white/5">
                        <h4 className="text-sm font-semibold text-zinc-100 mb-3">Section Metadata</h4>
                        <div className="space-y-2 text-xs text-zinc-400">
                            <p>Version: <span className="font-mono text-zinc-300">v{activeSection?.version ?? 1}</span></p>
                            <p>Locked: <span className="font-mono text-zinc-300">{activeSection?.humanEdited ? "Yes" : "No"}</span></p>
                            <p>Sources: <span className="font-mono text-zinc-300">{activeSection?.sourceChunkIds?.length ?? 0}</span></p>
                            <p>Snapshot: <span className="font-mono text-zinc-300">{activeSection?.snapshotId ?? "-"}</span></p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
