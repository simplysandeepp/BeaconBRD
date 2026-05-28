"use client";

import { useEffect, useRef, useState } from 'react';
import { Zap, CheckCircle2, Loader2, Eye, AlertTriangle } from 'lucide-react';
import { motion } from 'framer-motion';
import { streamBRDGeneration, type BRDStreamEventPayload } from '@/lib/apiClient';

type AgentType =
    | 'functional_requirements'
    | 'stakeholder_analysis'
    | 'timeline'
    | 'decisions'
    | 'assumptions'
    | 'success_metrics'
    | 'executive_summary'
    | 'validation';

type AgentStatus = 'idle' | 'working' | 'done' | 'error';

const agents = [
    { id: 'functional_requirements' as AgentType, name: 'Functional Requirements Agent', description: 'Extracts and drafts system requirements', icon: 'FR' },
    { id: 'stakeholder_analysis' as AgentType, name: 'Stakeholder Analysis Agent', description: 'Builds stakeholder mapping and concerns', icon: 'SA' },
    { id: 'timeline' as AgentType, name: 'Timeline Agent', description: 'Compiles milestones and deadlines', icon: 'TL' },
    { id: 'decisions' as AgentType, name: 'Decisions Agent', description: 'Collects confirmed project decisions', icon: 'DC' },
    { id: 'assumptions' as AgentType, name: 'Assumptions Agent', description: 'Infers assumptions requiring validation', icon: 'AS' },
    { id: 'success_metrics' as AgentType, name: 'Success Metrics Agent', description: 'Defines measurable outcome metrics', icon: 'SM' },
    { id: 'executive_summary' as AgentType, name: 'Executive Summary Agent', description: 'Synthesizes final BRD summary', icon: 'EX' },
    { id: 'validation' as AgentType, name: 'Validation Agent', description: 'Runs validation checks after generation', icon: 'VD' },
];

export default function AgentOrchestrator({ projectId }: { projectId: string }) {
    const [agentStatuses, setAgentStatuses] = useState<Record<AgentType, AgentStatus>>({
        functional_requirements: 'idle',
        stakeholder_analysis: 'idle',
        timeline: 'idle',
        decisions: 'idle',
        assumptions: 'idle',
        success_metrics: 'idle',
        executive_summary: 'idle',
        validation: 'idle',
    });
    const [isGenerating, setIsGenerating] = useState(false);
    const [thoughtProcess, setThoughtProcess] = useState<string[]>([]);
    const [error, setError] = useState<string | null>(null);
    const streamCleanupRef = useRef<(() => void) | null>(null);

    useEffect(() => {
        return () => {
            streamCleanupRef.current?.();
            streamCleanupRef.current = null;
        };
    }, []);

    const appendThought = (line: string) => {
        setThoughtProcess((prev) => [...prev, line]);
    };

    const resetStatuses = () => {
        setAgentStatuses({
            functional_requirements: 'idle',
            stakeholder_analysis: 'idle',
            timeline: 'idle',
            decisions: 'idle',
            assumptions: 'idle',
            success_metrics: 'idle',
            executive_summary: 'idle',
            validation: 'idle',
        });
    };

    const markAgent = (agent: AgentType, status: AgentStatus) => {
        setAgentStatuses((prev) => ({ ...prev, [agent]: status }));
    };

    const mapAgentName = (agent: string): AgentType | null => {
        if (
            agent === 'functional_requirements' ||
            agent === 'stakeholder_analysis' ||
            agent === 'timeline' ||
            agent === 'decisions' ||
            agent === 'assumptions' ||
            agent === 'success_metrics' ||
            agent === 'executive_summary' ||
            agent === 'validation'
        ) {
            return agent;
        }
        return null;
    };

    const startGeneration = async () => {
        streamCleanupRef.current?.();
        streamCleanupRef.current = null;

        setIsGenerating(true);
        setThoughtProcess([]);
        setError(null);
        resetStatuses();

        const sessionId = projectId;
        const applyEvent = (payload: BRDStreamEventPayload) => {
            switch (payload.type) {
                case 'generation_started':
                    appendThought('[SYSTEM] BRD generation started');
                    break;
                case 'snapshot_created':
                    appendThought('[SYSTEM] Snapshot created');
                    break;
                case 'agents_launched':
                    appendThought('[SYSTEM] Parallel agents launched');
                    break;
                case 'agent_started': {
                    const mapped = mapAgentName(payload.agent ?? '');
                    if (mapped) {
                        markAgent(mapped, 'working');
                        appendThought(`[${mapped.toUpperCase()}] Started`);
                    }
                    break;
                }
                case 'agent_completed': {
                    const mapped = mapAgentName(payload.agent ?? '');
                    if (mapped) {
                        markAgent(mapped, 'done');
                        appendThought(`[${mapped.toUpperCase()}] Completed`);
                    }
                    break;
                }
                case 'agent_failed': {
                    const mapped = mapAgentName(payload.agent ?? '');
                    if (mapped) {
                        markAgent(mapped, 'error');
                    }
                    appendThought(`[${(payload.agent ?? 'UNKNOWN').toUpperCase()}] Failed: ${payload.error ?? 'Unknown error'}`);
                    break;
                }
                case 'generation_completed':
                    appendThought('[SYSTEM] Section generation completed');
                    break;
                case 'validation_started':
                    markAgent('validation', 'working');
                    appendThought('[VALIDATION] Started');
                    break;
                case 'validation_completed':
                    markAgent('validation', 'done');
                    appendThought('[VALIDATION] Completed');
                    break;
                case 'complete':
                    appendThought('[SYSTEM] BRD generation completed');
                    setIsGenerating(false);
                    streamCleanupRef.current = null;
                    break;
                case 'error':
                    setError(payload.message ?? 'Generation failed');
                    setIsGenerating(false);
                    appendThought(`[SYSTEM] ERROR: ${payload.message ?? 'Generation failed'}`);
                    streamCleanupRef.current = null;
                    break;
                default:
                    if (payload.message) {
                        appendThought(`[SYSTEM] ${payload.message}`);
                    }
                    break;
            }
        };

        streamCleanupRef.current = streamBRDGeneration(sessionId, {
            onEvent: applyEvent,
            onDone: () => {
                setIsGenerating(false);
                streamCleanupRef.current = null;
            },
            onError: (message) => {
                setError(message);
                setIsGenerating(false);
                appendThought(`[SYSTEM] ${message}`);
                streamCleanupRef.current = null;
            },
        });
    };

    return (
        <div className="space-y-6">
            {/* Control Panel */}
            <div className="flex items-center justify-between">
                <div>
                    <h3 className="text-lg font-semibold text-zinc-100">AI Agent Workflow</h3>
                    <p className="text-sm text-zinc-400 mt-1">Multi-agent system for BRD generation</p>
                </div>
                <button
                    onClick={startGeneration}
                    disabled={isGenerating || !projectId}
                    className="flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-cyan-500 to-blue-500 hover:from-cyan-600 hover:to-blue-600 disabled:from-zinc-800 disabled:to-zinc-800 disabled:text-zinc-500 text-white rounded-lg font-medium shadow-lg shadow-cyan-500/20 transition-all"
                >
                    <Zap size={18} />
                    {isGenerating ? 'Generating...' : 'Start BRD Generation'}
                </button>
            </div>

            {error && (
                <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
                    <AlertTriangle size={14} />
                    {error}
                </div>
            )}

            {/* Agent Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
                {agents.map((agent, index) => {
                    const status = agentStatuses[agent.id];
                    const isActive = status === 'working';

                    return (
                        <motion.div
                            key={agent.id}
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: index * 0.1 }}
                            className={`bg-zinc-900/50 border rounded-xl p-6 transition-all ${isActive ? 'border-cyan-500 shadow-lg shadow-cyan-500/20' : status === 'done' ? 'border-green-500/50' : 'border-white/5'
                                }`}
                        >
                            <div className="text-sm font-mono text-zinc-300 mb-3">{agent.icon}</div>
                            <h4 className="font-semibold text-zinc-100 mb-1">{agent.name}</h4>
                            <p className="text-xs text-zinc-400 mb-4">{agent.description}</p>

                            <div className="flex items-center justify-between">
                                {status === 'idle' && <span className="text-xs text-zinc-500">Idle</span>}
                                {status === 'working' && (
                                    <div className="flex items-center gap-2 text-cyan-400 text-xs">
                                        <Loader2 size={12} className="animate-spin" />
                                        Working
                                    </div>
                                )}
                                {status === 'done' && (
                                    <div className="flex items-center gap-2 text-green-400 text-xs">
                                        <CheckCircle2 size={12} />
                                        Complete
                                    </div>
                                )}
                                {status === 'error' && (
                                    <div className="flex items-center gap-2 text-red-400 text-xs">
                                        <AlertTriangle size={12} />
                                        Failed
                                    </div>
                                )}
                            </div>
                        </motion.div>
                    );
                })}
            </div>

            {/* Thought Process Feed */}
            <div className="bg-zinc-900/50 border border-white/5 rounded-xl p-6">
                <div className="flex items-center gap-2 mb-4">
                    <Eye size={18} className="text-purple-400" />
                    <h4 className="font-semibold text-zinc-100">Agent Thought Process</h4>
                </div>

                <div className="bg-black/50 rounded-lg p-4 h-[300px] overflow-y-auto font-mono text-sm">
                    {thoughtProcess.length === 0 ? (
                        <p className="text-zinc-600 text-center py-12">Agent thoughts will appear here during generation...</p>
                    ) : (
                        <div className="space-y-2">
                            {thoughtProcess.map((thought, index) => (
                                <motion.div
                                    key={index}
                                    initial={{ opacity: 0, x: -20 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    className="text-purple-400"
                                >
                                    {thought}
                                </motion.div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
