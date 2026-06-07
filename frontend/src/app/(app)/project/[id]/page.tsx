"use client";

import { useProjectStore } from '@/store/useProjectStore';
import { notFound } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import { useEffect } from 'react';
import { useSessionStore } from '@/store/useSessionStore';

export default function ProjectPage({ params }: { params: { id: string } }) {
    const { id } = params;
    const projects = useProjectStore((state) => state.projects);
    const project = projects.find((p) => p.id === id);
    const { setActive } = useSessionStore();

    if (!project) {
        notFound();
    }

    useEffect(() => {
        setActive(id);
    }, [id, setActive]);

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <Link
                        href="/dashboard"
                        className="p-2 hover:bg-white/5 rounded-lg transition-colors text-zinc-400 hover:text-zinc-100"
                    >
                        <ArrowLeft size={20} />
                    </Link>
                    <div>
                        <h1 className="text-2xl font-semibold text-zinc-100">{project.name}</h1>
                        {project.description && (
                            <p className="text-zinc-400 text-sm mt-0.5">{project.description}</p>
                        )}
                    </div>
                </div>
            </div>

            <div className="glass-card rounded-xl p-5">
                <p className="text-sm text-zinc-300">
                    This route now uses the live backend-connected modules.
                </p>
                <div className="flex flex-wrap items-center gap-3 mt-4">
                    <Link href="/ingestion" className="btn-secondary text-sm py-2 px-4">
                        Open Ingestion
                    </Link>
                    <Link href="/agents" className="btn-secondary text-sm py-2 px-4">
                        Open Agent Orchestrator
                    </Link>
                    <Link href="/brd" className="btn-primary text-sm py-2 px-4">
                        Open BRD Editor
                    </Link>
                </div>
            </div>
        </div>
    );
}
