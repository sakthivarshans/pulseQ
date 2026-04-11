import React, { useState, useEffect, useCallback } from 'react';
import api from '../../services/api';
import {
    Zap, Shield, Eye, AlertTriangle, Cpu, Brain,
    Code2, Trash2, ChevronDown, ChevronRight,
    ThumbsUp, ThumbsDown, GitPullRequest, X,
    TrendingUp, Clock, Filter, Sparkles, RefreshCw,
    FileCode2, CheckCircle2, ArrowRight, Loader2,
    Bot, Terminal, FolderOpen
} from 'lucide-react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';

interface Suggestion {
    id: string;
    file_path: string;
    language: string;
    line_start: number;
    line_end: number;
    category: string;
    priority: string;
    title: string;
    problem: string;
    solution: string;
    code_before: string;
    code_after: string;
    performance_impact: string;
    effort: string;
    status: string;
    upvotes: number;
    downvotes: number;
    pr_url: string | null;
}

interface Summary {
    total: number;
    by_priority: Record<string, number>;
    by_category: Record<string, number>;
    files_with_suggestions: Array<{ file_path: string; count: number }>;
}

const PRIORITY_META: Record<string, { label: string; color: string; dot: string; ring: string }> = {
    critical: { label: 'Critical', color: '#DC2626', dot: '#FEE2E2', ring: 'rgba(220,38,38,0.15)' },
    high: { label: 'High', color: '#EA580C', dot: '#FFEDD5', ring: 'rgba(234,88,12,0.15)' },
    medium: { label: 'Medium', color: '#CA8A04', dot: '#FEF9C3', ring: 'rgba(202,138,4,0.15)' },
    low: { label: 'Low', color: '#2563EB', dot: '#DBEAFE', ring: 'rgba(37,99,235,0.12)' },
};

const CAT_META: Record<string, { icon: React.ReactNode; label: string; color: string }> = {
    performance: { icon: <Zap size={12} />, label: 'Performance', color: '#F97316' },
    security: { icon: <Shield size={12} />, label: 'Security', color: '#EF4444' },
    readability: { icon: <Eye size={12} />, label: 'Readability', color: '#3B82F6' },
    error_handling: { icon: <AlertTriangle size={12} />, label: 'Error Handling', color: '#EAB308' },
    memory: { icon: <Cpu size={12} />, label: 'Memory', color: '#8B5CF6' },
    algorithm: { icon: <Brain size={12} />, label: 'Algorithm', color: '#6366F1' },
    best_practice: { icon: <Code2 size={12} />, label: 'Best Practice', color: '#10B981' },
    redundancy: { icon: <Trash2 size={12} />, label: 'Redundancy', color: '#6B7280' },
};

// ──────────────────────────────────────────────────────────────
// Main Component
// ──────────────────────────────────────────────────────────────
export default function ImprovementsTab({
    repoId,
    analyzing,
    onReanalyze,
}: {
    repoId: string;
    analyzing: boolean;
    onReanalyze: () => void;
}) {
    const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
    const [summary, setSummary] = useState<Summary | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [selectedFile, setSelectedFile] = useState<string | null>(null);
    const [activeSuggestion, setActiveSuggestion] = useState<Suggestion | null>(null);
    const [filterCat, setFilterCat] = useState<string>('all');
    const [filterPri, setFilterPri] = useState<string>('all');
    const [applyingFix, setApplyingFix] = useState<string | null>(null);
    const [votedIds, setVotedIds] = useState<Set<string>>(new Set());
    const [scanMsg, setScanMsg] = useState('Scanning repository…');

    // Animated scan messages
    useEffect(() => {
        if (!analyzing) return;
        const msgs = [
            'Scanning repository…',
            'Reading source files…',
            'Sending code to AI…',
            'Detecting optimization opportunities…',
            'Analyzing patterns…',
            'Generating suggestions…',
        ];
        let i = 0;
        const iv = setInterval(() => {
            i = (i + 1) % msgs.length;
            setScanMsg(msgs[i]);
        }, 2200);
        return () => clearInterval(iv);
    }, [analyzing]);

    const fetchData = useCallback(async () => {
        try {
            setLoading(true);
            setError(null);
            const qs: Record<string, string> = { status: 'open', per_page: '200' };
            if (filterCat !== 'all') qs.category = filterCat;
            if (filterPri !== 'all') qs.priority = filterPri;
            const params = new URLSearchParams(qs).toString();
            const [sData, sumData]: [any, any] = await Promise.all([
                api.get(`/repositories/${repoId}/suggestions?${params}`).catch(() => ({ suggestions: [] })),
                api.get(`/repositories/${repoId}/suggestions/summary`).catch(() => ({})),
            ]);
            setSuggestions(sData.suggestions || []);
            setSummary(sumData);
            if (sData.suggestions?.length > 0) {
                const firstFile = sData.suggestions[0].file_path;
                setSelectedFile(f => f || firstFile);
            }
        } catch (e: any) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    }, [repoId, filterCat, filterPri]);

    useEffect(() => { fetchData(); }, [fetchData]);

    // Re-fetch when analysis completes
    useEffect(() => {
        if (!analyzing) {
            const t = setTimeout(fetchData, 800);
            return () => clearTimeout(t);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [analyzing]);

    const handleVote = async (id: string, feedback: 'upvote' | 'downvote') => {
        if (votedIds.has(id)) return;
        try {
            const r: any = await api.post(`/repositories/${repoId}/suggestions/${id}/feedback`, { feedback });
            setSuggestions(prev => prev.map(s => s.id === id ? { ...s, upvotes: r.upvotes, downvotes: r.downvotes } : s));
            if (activeSuggestion?.id === id) setActiveSuggestion(a => a ? { ...a, upvotes: r.upvotes, downvotes: r.downvotes } : a);
            setVotedIds(prev => new Set([...prev, id]));
        } catch { /* ignore */ }
    };

    const handleApplyFix = async (id: string) => {
        setApplyingFix(id);
        try {
            const r: any = await api.post(`/repositories/${repoId}/suggestions/${id}/apply-fix`, {});
            setSuggestions(prev => prev.map(s => s.id === id ? { ...s, status: 'pr_created', pr_url: r.pr_url } : s));
            if (activeSuggestion?.id === id) setActiveSuggestion(a => a ? { ...a, status: 'pr_created', pr_url: r.pr_url } : a);
            window.open(r.pr_url, '_blank');
        } catch (e: any) {
            alert(`Could not create PR: ${e.message}`);
        } finally {
            setApplyingFix(null);
        }
    };

    const handleDismiss = async (id: string) => {
        try {
            await api.post(`/repositories/${repoId}/suggestions/${id}/dismiss`, {});
            setSuggestions(prev => prev.filter(s => s.id !== id));
            if (activeSuggestion?.id === id) setActiveSuggestion(null);
        } catch { /* ignore */ }
    };

    // ── Derived data ──────────────────────────────────────────
    const files = Array.from(new Set(suggestions.map(s => s.file_path)));
    const visibleSuggestions = selectedFile
        ? suggestions.filter(s => s.file_path === selectedFile)
        : suggestions;

    // ── Analyzing overlay ─────────────────────────────────────
    if (analyzing) {
        return (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 420, gap: 24 }}>
                <div style={{
                    width: 72, height: 72,
                    background: 'linear-gradient(135deg, #6366F1, #4F46E5)',
                    borderRadius: '50%',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    boxShadow: '0 0 0 12px rgba(99,102,241,0.1), 0 0 0 24px rgba(99,102,241,0.05)',
                    animation: 'pulse 2s ease-in-out infinite',
                }}>
                    <Bot size={32} color="#fff" />
                </div>
                <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 18, fontWeight: 700, color: '#0F172A', marginBottom: 8 }}>
                        AI is analyzing your code
                    </div>
                    <div style={{ fontSize: 14, color: '#6366F1', fontWeight: 500, minHeight: 22, transition: 'all 0.3s' }}>
                        {scanMsg}
                    </div>
                    <div style={{ fontSize: 12, color: '#94A3B8', marginTop: 8 }}>
                        This may take 30–120 seconds depending on repository size
                    </div>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                    {[0, 1, 2].map(i => (
                        <div key={i} style={{
                            width: 8, height: 8, borderRadius: '50%',
                            background: '#6366F1',
                            opacity: 0.3,
                            animation: `bounce 1.2s ${i * 0.2}s ease-in-out infinite`,
                        }} />
                    ))}
                </div>
                <style>{`
          @keyframes pulse { 0%,100%{box-shadow:0 0 0 12px rgba(99,102,241,0.1),0 0 0 24px rgba(99,102,241,0.05)} 50%{box-shadow:0 0 0 16px rgba(99,102,241,0.15),0 0 0 32px rgba(99,102,241,0.07)} }
          @keyframes bounce { 0%,100%{opacity:0.3;transform:translateY(0)} 50%{opacity:1;transform:translateY(-6px)} }
        `}</style>
            </div>
        );
    }

    // ── Empty state ────────────────────────────────────────────
    if (!loading && !error && suggestions.length === 0) {
        return (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 380, gap: 20, padding: 32 }}>
                <div style={{
                    width: 80, height: 80,
                    background: 'linear-gradient(135deg, #EEF2FF, #E0E7FF)',
                    borderRadius: '50%',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                    <Sparkles size={36} color="#6366F1" />
                </div>
                <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 20, fontWeight: 700, color: '#0F172A', marginBottom: 8 }}>
                        No suggestions yet
                    </div>
                    <div style={{ fontSize: 14, color: '#64748B', marginBottom: 24, maxWidth: 360, lineHeight: 1.6 }}>
                        Click <strong style={{ color: '#6366F1' }}>Analyze Code</strong> to let the AI scan your repository and surface optimization opportunities, security issues, and performance wins.
                    </div>
                    <button
                        onClick={onReanalyze}
                        style={{
                            display: 'inline-flex', alignItems: 'center', gap: 8,
                            padding: '12px 24px', borderRadius: 10, border: 'none', cursor: 'pointer',
                            background: 'linear-gradient(135deg, #6366F1, #4F46E5)',
                            color: '#fff', fontSize: 14, fontWeight: 600,
                            boxShadow: '0 4px 14px rgba(99,102,241,0.35)',
                            transition: 'all 0.2s',
                        }}
                    >
                        <Zap size={16} /> Analyze Code Now
                    </button>
                </div>
            </div>
        );
    }

    // ── Main IDE layout ────────────────────────────────────────
    return (
        <div style={{ display: 'flex', height: '100%', minHeight: 560, background: '#F8FAFC', borderRadius: 12, overflow: 'hidden', border: '1px solid #E2E8F0' }}>

            {/* LEFT: File Tree */}
            <div style={{
                width: 240, flexShrink: 0,
                background: '#1E1E2E',
                display: 'flex', flexDirection: 'column',
                borderRight: '1px solid #2D2D3F',
            }}>
                {/* Header */}
                <div style={{
                    padding: '12px 14px',
                    borderBottom: '1px solid #2D2D3F',
                    display: 'flex', alignItems: 'center', gap: 8,
                }}>
                    <FolderOpen size={14} color="#7C3AED" />
                    <span style={{ fontSize: 11, fontWeight: 700, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                        Files
                    </span>
                    <span style={{ marginLeft: 'auto', fontSize: 10, background: '#3730A3', color: '#A5B4FC', padding: '1px 6px', borderRadius: 8, fontWeight: 700 }}>
                        {files.length}
                    </span>
                </div>

                {/* File list */}
                <div style={{ flex: 1, overflowY: 'auto', padding: '6px 0' }}>
                    {loading ? (
                        [1, 2, 3, 4].map(i => (
                            <div key={i} style={{ margin: '6px 10px', height: 28, borderRadius: 6, background: '#2D2D3F', opacity: 0.6 }} />
                        ))
                    ) : (
                        files.map(fp => {
                            const fileSugs = suggestions.filter(s => s.file_path === fp);
                            const hasCritical = fileSugs.some(s => s.priority === 'critical');
                            const hasHigh = fileSugs.some(s => s.priority === 'high');
                            const dotColor = hasCritical ? '#EF4444' : hasHigh ? '#F97316' : '#EAB308';
                            const isSelected = selectedFile === fp;
                            const fileName = fp.split('/').pop() || fp;
                            const dir = fp.includes('/') ? fp.substring(0, fp.lastIndexOf('/') + 1) : '';
                            return (
                                <button
                                    key={fp}
                                    onClick={() => { setSelectedFile(fp); setActiveSuggestion(null); }}
                                    style={{
                                        width: '100%', border: 'none', textAlign: 'left',
                                        display: 'flex', alignItems: 'center', gap: 8,
                                        padding: '7px 14px',
                                        background: isSelected ? 'rgba(99,102,241,0.15)' : 'transparent',
                                        borderLeft: isSelected ? '2px solid #6366F1' : '2px solid transparent',
                                        cursor: 'pointer',
                                        transition: 'all 0.1s',
                                    }}
                                >
                                    <FileCode2 size={13} color={isSelected ? '#818CF8' : '#64748B'} style={{ flexShrink: 0 }} />
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        {dir && <div style={{ fontSize: 9, color: '#475569', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{dir}</div>}
                                        <div style={{ fontSize: 12, color: isSelected ? '#C7D2FE' : '#94A3B8', fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                            {fileName}
                                        </div>
                                    </div>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 3, flexShrink: 0 }}>
                                        <span style={{ width: 6, height: 6, borderRadius: '50%', background: dotColor, display: 'inline-block' }} />
                                        <span style={{ fontSize: 10, color: '#64748B', fontWeight: 600 }}>{fileSugs.length}</span>
                                    </div>
                                </button>
                            );
                        })
                    )}
                </div>

                {/* Stats footer */}
                {summary && !loading && (
                    <div style={{ borderTop: '1px solid #2D2D3F', padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 4 }}>
                        {Object.entries(PRIORITY_META).map(([p, meta]) => {
                            const count = summary.by_priority[p] || 0;
                            return count > 0 ? (
                                <div key={p} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                    <span style={{ fontSize: 11, color: '#64748B' }}>{meta.label}</span>
                                    <span style={{ fontSize: 11, fontWeight: 700, color: meta.color }}>{count}</span>
                                </div>
                            ) : null;
                        })}
                        <div style={{ borderTop: '1px solid #2D2D3F', marginTop: 4, paddingTop: 4, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                            <span style={{ fontSize: 11, color: '#64748B' }}>Total</span>
                            <span style={{ fontSize: 11, fontWeight: 700, color: '#94A3B8' }}>{summary.total}</span>
                        </div>
                    </div>
                )}
            </div>

            {/* MIDDLE: Suggestions List */}
            <div style={{
                width: 340, flexShrink: 0,
                background: '#FFFFFF',
                borderRight: '1px solid #E2E8F0',
                display: 'flex', flexDirection: 'column',
            }}>
                {/* Toolbar */}
                <div style={{ padding: '10px 12px', borderBottom: '1px solid #F1F5F9', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flex: 1 }}>
                        <Bot size={14} color="#6366F1" />
                        <span style={{ fontSize: 12, fontWeight: 700, color: '#0F172A' }}>
                            {selectedFile ? `${(selectedFile.split('/').pop())} suggestions` : `All suggestions`}
                        </span>
                        <span style={{ fontSize: 11, color: '#6366F1', background: '#EEF2FF', padding: '1px 6px', borderRadius: 8, fontWeight: 700 }}>
                            {visibleSuggestions.length}
                        </span>
                    </div>
                    <button onClick={onReanalyze} title="Re-analyze" style={{ border: 'none', background: 'none', cursor: 'pointer', padding: 4, color: '#94A3B8', display: 'flex', alignItems: 'center' }}>
                        <RefreshCw size={13} />
                    </button>
                </div>

                {/* Filter chips */}
                <div style={{ padding: '8px 12px', borderBottom: '1px solid #F1F5F9', display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                    {Object.entries(PRIORITY_META).map(([p, meta]) => (
                        <button
                            key={p}
                            onClick={() => setFilterPri(filterPri === p ? 'all' : p)}
                            style={{
                                fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 20,
                                border: `1px solid ${filterPri === p ? meta.color : '#E2E8F0'}`,
                                background: filterPri === p ? meta.ring : 'transparent',
                                color: filterPri === p ? meta.color : '#64748B',
                                cursor: 'pointer', transition: 'all 0.15s',
                            }}
                        >
                            {meta.label}
                        </button>
                    ))}
                    {filterCat !== 'all' || filterPri !== 'all' ? (
                        <button
                            onClick={() => { setFilterCat('all'); setFilterPri('all'); }}
                            style={{ fontSize: 10, padding: '2px 8px', borderRadius: 20, border: '1px solid #E2E8F0', background: 'none', color: '#94A3B8', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 3 }}
                        >
                            <X size={10} /> Clear
                        </button>
                    ) : null}
                </div>

                {/* Suggestion list */}
                <div style={{ flex: 1, overflowY: 'auto' }}>
                    {loading ? (
                        <div style={{ padding: 24, textAlign: 'center', color: '#94A3B8' }}>
                            <Loader2 size={20} style={{ animation: 'spin 1s linear infinite', margin: '0 auto 8px' }} />
                            <div style={{ fontSize: 12 }}>Loading suggestions…</div>
                        </div>
                    ) : visibleSuggestions.length === 0 ? (
                        <div style={{ padding: 32, textAlign: 'center' }}>
                            <CheckCircle2 size={24} color="#10B981" style={{ margin: '0 auto 8px' }} />
                            <div style={{ fontSize: 13, color: '#64748B' }}>No issues in this file</div>
                        </div>
                    ) : (
                        visibleSuggestions.map(s => {
                            const meta = PRIORITY_META[s.priority] || PRIORITY_META.low;
                            const cat = CAT_META[s.category] || CAT_META.best_practice;
                            const isActive = activeSuggestion?.id === s.id;
                            const isPRd = s.status === 'pr_created';
                            return (
                                <button
                                    key={s.id}
                                    onClick={() => setActiveSuggestion(isActive ? null : s)}
                                    style={{
                                        width: '100%', border: 'none', textAlign: 'left',
                                        padding: '12px 14px',
                                        background: isActive ? '#F0F4FF' : isPRd ? '#F0FDF4' : 'transparent',
                                        borderBottom: '1px solid #F8FAFC',
                                        borderLeft: `3px solid ${isActive ? '#6366F1' : isPRd ? '#10B981' : 'transparent'}`,
                                        cursor: 'pointer', transition: 'all 0.1s',
                                        display: 'flex', flexDirection: 'column', gap: 5,
                                    }}
                                >
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'space-between' }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 5, overflow: 'hidden' }}>
                                            <span style={{ color: cat.color, flexShrink: 0 }}>{cat.icon}</span>
                                            <span style={{ fontSize: 12, fontWeight: 600, color: '#0F172A', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                                {s.title}
                                            </span>
                                        </div>
                                        {isPRd ? (
                                            <span style={{ fontSize: 9, fontWeight: 700, color: '#10B981', background: '#DCFCE7', padding: '1px 6px', borderRadius: 8, flexShrink: 0 }}>PR Created</span>
                                        ) : (
                                            <span style={{ fontSize: 9, fontWeight: 700, color: meta.color, background: meta.dot, padding: '1px 6px', borderRadius: 8, flexShrink: 0 }}>
                                                {meta.label}
                                            </span>
                                        )}
                                    </div>
                                    <div style={{ fontSize: 11, color: '#64748B', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                        {s.problem}
                                    </div>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 10, color: '#94A3B8' }}>
                                        <span>L{s.line_start}–{s.line_end}</span>
                                        <span>·</span>
                                        <span>{s.effort} effort</span>
                                        <span style={{ marginLeft: 'auto' }}>{s.performance_impact}</span>
                                    </div>
                                </button>
                            );
                        })
                    )}
                </div>
            </div>

            {/* RIGHT: Detail Panel */}
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: '#FAFBFF' }}>
                {activeSuggestion ? (
                    <DetailPanel
                        s={activeSuggestion}
                        applying={applyingFix === activeSuggestion.id}
                        voted={votedIds.has(activeSuggestion.id)}
                        onVote={handleVote}
                        onApplyFix={handleApplyFix}
                        onDismiss={handleDismiss}
                        onClose={() => setActiveSuggestion(null)}
                    />
                ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', flex: 1, gap: 16, padding: 32, textAlign: 'center' }}>
                        <div style={{ width: 56, height: 56, background: '#EEF2FF', borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                            <Terminal size={26} color="#6366F1" />
                        </div>
                        <div>
                            <div style={{ fontSize: 16, fontWeight: 700, color: '#1E293B', marginBottom: 6 }}>Select a suggestion</div>
                            <div style={{ fontSize: 13, color: '#64748B', lineHeight: 1.6, maxWidth: 300 }}>
                                Click any suggestion on the left to see the detailed analysis, before/after code diff, and apply the AI fix.
                            </div>
                        </div>
                        {summary && summary.total > 0 && (
                            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'center', marginTop: 8 }}>
                                {Object.entries(PRIORITY_META).map(([p, meta]) => {
                                    const count = summary.by_priority[p] || 0;
                                    return count > 0 ? (
                                        <div key={p} style={{
                                            padding: '6px 14px', borderRadius: 20,
                                            background: meta.dot,
                                            border: `1px solid ${meta.color}30`,
                                        }}>
                                            <span style={{ fontSize: 16, fontWeight: 800, color: meta.color }}>{count}</span>
                                            <span style={{ fontSize: 11, color: meta.color, marginLeft: 4 }}>{meta.label}</span>
                                        </div>
                                    ) : null;
                                })}
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}

// ──────────────────────────────────────────────────────────────
// Detail Panel
// ──────────────────────────────────────────────────────────────
function DetailPanel({ s, applying, voted, onVote, onApplyFix, onDismiss, onClose }: {
    s: Suggestion;
    applying: boolean;
    voted: boolean;
    onVote: (id: string, f: 'upvote' | 'downvote') => void;
    onApplyFix: (id: string) => void;
    onDismiss: (id: string) => void;
    onClose: () => void;
}) {
    const meta = PRIORITY_META[s.priority] || PRIORITY_META.low;
    const cat = CAT_META[s.category] || CAT_META.best_practice;
    const [showAfter, setShowAfter] = useState(false);

    return (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
            {/* Header */}
            <div style={{
                padding: '14px 20px', borderBottom: '1px solid #E2E8F0',
                background: '#fff',
                display: 'flex', alignItems: 'flex-start', gap: 12,
            }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, fontWeight: 700, color: cat.color, background: `${cat.color}15`, padding: '2px 8px', borderRadius: 20 }}>
                            {cat.icon} {cat.label}
                        </span>
                        <span style={{ fontSize: 11, fontWeight: 700, color: meta.color, background: meta.dot, padding: '2px 8px', borderRadius: 20 }}>
                            {meta.label} Priority
                        </span>
                        <span style={{ fontSize: 11, color: '#64748B', marginLeft: 'auto' }}>
                            Lines {s.line_start}–{s.line_end}
                        </span>
                    </div>
                    <h2 style={{ fontSize: 15, fontWeight: 700, color: '#0F172A', margin: 0, lineHeight: 1.4 }}>{s.title}</h2>
                    <div style={{ fontSize: 11, fontFamily: 'monospace', color: '#6366F1', marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {s.file_path}
                    </div>
                </div>
                <button onClick={onClose} style={{ border: 'none', background: 'none', cursor: 'pointer', color: '#94A3B8', padding: 4, flexShrink: 0 }}>
                    <X size={16} />
                </button>
            </div>

            {/* Body */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 16 }}>

                {/* Problem */}
                <section>
                    <div style={{ fontSize: 11, fontWeight: 700, color: '#EF4444', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 5 }}>
                        <AlertTriangle size={11} /> Problem
                    </div>
                    <p style={{ fontSize: 13, color: '#374151', lineHeight: 1.7, margin: 0 }}>{s.problem}</p>
                </section>

                {/* Solution */}
                <section>
                    <div style={{ fontSize: 11, fontWeight: 700, color: '#10B981', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 5 }}>
                        <Sparkles size={11} /> AI Solution
                    </div>
                    <p style={{ fontSize: 13, color: '#374151', lineHeight: 1.7, margin: 0 }}>{s.solution}</p>
                </section>

                {/* Impact & Effort */}
                <div style={{ display: 'flex', gap: 10 }}>
                    <div style={{ flex: 1, background: '#F0FDF4', border: '1px solid #BBF7D0', borderRadius: 10, padding: '10px 14px' }}>
                        <div style={{ fontSize: 10, fontWeight: 700, color: '#059669', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 3, display: 'flex', alignItems: 'center', gap: 4 }}>
                            <TrendingUp size={10} /> Impact
                        </div>
                        <div style={{ fontSize: 13, fontWeight: 600, color: '#065F46' }}>{s.performance_impact}</div>
                    </div>
                    <div style={{ flex: 1, background: '#EFF6FF', border: '1px solid #BFDBFE', borderRadius: 10, padding: '10px 14px' }}>
                        <div style={{ fontSize: 10, fontWeight: 700, color: '#2563EB', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 3, display: 'flex', alignItems: 'center', gap: 4 }}>
                            <Clock size={10} /> Effort
                        </div>
                        <div style={{ fontSize: 13, fontWeight: 600, color: '#1E3A8A', textTransform: 'capitalize' }}>{s.effort}</div>
                    </div>
                </div>

                {/* Code diff */}
                {(s.code_before || s.code_after) && (
                    <section>
                        <div style={{ fontSize: 11, fontWeight: 700, color: '#64748B', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 5 }}>
                            <Code2 size={11} /> Code Change
                        </div>

                        {/* Toggle Before/After */}
                        <div style={{ display: 'flex', borderRadius: 8, overflow: 'hidden', border: '1px solid #E2E8F0', marginBottom: 10, width: 'fit-content' }}>
                            <button
                                onClick={() => setShowAfter(false)}
                                style={{
                                    padding: '5px 14px', fontSize: 12, fontWeight: 600, border: 'none', cursor: 'pointer',
                                    background: !showAfter ? '#DC2626' : '#F8FAFC',
                                    color: !showAfter ? '#fff' : '#64748B',
                                    transition: 'all 0.15s',
                                    display: 'flex', alignItems: 'center', gap: 5,
                                }}
                            >
                                <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: !showAfter ? '#fff' : '#DC2626' }} />
                                Before
                            </button>
                            <button
                                onClick={() => setShowAfter(true)}
                                style={{
                                    padding: '5px 14px', fontSize: 12, fontWeight: 600, border: 'none', cursor: 'pointer',
                                    background: showAfter ? '#059669' : '#F8FAFC',
                                    color: showAfter ? '#fff' : '#64748B',
                                    transition: 'all 0.15s',
                                    display: 'flex', alignItems: 'center', gap: 5,
                                }}
                            >
                                <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: showAfter ? '#fff' : '#059669' }} />
                                After (AI Fix)
                            </button>
                        </div>

                        <div style={{ borderRadius: 10, overflow: 'hidden', border: `1px solid ${showAfter ? '#BBF7D0' : '#FECACA'}` }}>
                            <div style={{ padding: '6px 14px', background: showAfter ? '#DCFCE7' : '#FEE2E2', display: 'flex', alignItems: 'center', gap: 6 }}>
                                <ArrowRight size={11} color={showAfter ? '#059669' : '#DC2626'} />
                                <span style={{ fontSize: 11, fontWeight: 700, color: showAfter ? '#065F46' : '#991B1B' }}>
                                    {showAfter ? 'Optimized version' : 'Current code'}
                                </span>
                                <span style={{ fontSize: 10, color: showAfter ? '#059669' : '#DC2626', marginLeft: 'auto', fontFamily: 'monospace' }}>
                                    {s.file_path} : {s.line_start}
                                </span>
                            </div>
                            <SyntaxHighlighter
                                language={s.language}
                                style={oneLight}
                                customStyle={{ margin: 0, fontSize: 12, lineHeight: 1.6, maxHeight: 280, background: showAfter ? '#F0FDF4' : '#FFF7F7' }}
                            >
                                {showAfter ? (s.code_after || '') : (s.code_before || '')}
                            </SyntaxHighlighter>
                        </div>
                    </section>
                )}
            </div>

            {/* Footer actions */}
            <div style={{
                padding: '12px 20px', borderTop: '1px solid #E2E8F0', background: '#fff',
                display: 'flex', alignItems: 'center', gap: 10,
            }}>
                {s.status === 'pr_created' && s.pr_url ? (
                    <a
                        href={s.pr_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{
                            flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                            padding: '10px 16px', borderRadius: 10, textDecoration: 'none',
                            background: '#DCFCE7', color: '#065F46', fontWeight: 700, fontSize: 13,
                            border: '1px solid #BBF7D0',
                        }}
                    >
                        <GitPullRequest size={15} /> View Pull Request ↗
                    </a>
                ) : (
                    <button
                        onClick={() => onApplyFix(s.id)}
                        disabled={applying}
                        style={{
                            flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                            padding: '10px 16px', borderRadius: 10, border: 'none', cursor: applying ? 'default' : 'pointer',
                            background: applying ? '#E2E8F0' : 'linear-gradient(135deg, #6366F1, #4F46E5)',
                            color: applying ? '#94A3B8' : '#fff', fontWeight: 700, fontSize: 13,
                            boxShadow: applying ? 'none' : '0 4px 12px rgba(99,102,241,0.3)',
                            transition: 'all 0.2s',
                        }}
                    >
                        {applying
                            ? <><Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> Creating PR…</>
                            : <><GitPullRequest size={15} /> Apply Fix — Create PR</>}
                    </button>
                )}

                {/* Vote */}
                <button
                    onClick={() => onVote(s.id, 'upvote')}
                    disabled={voted}
                    title="Helpful"
                    style={{
                        display: 'flex', alignItems: 'center', gap: 4, padding: '8px 12px',
                        borderRadius: 10, border: '1px solid #E2E8F0', background: voted ? '#F8FAFC' : '#fff',
                        color: voted ? '#CBD5E1' : '#10B981', cursor: voted ? 'default' : 'pointer', fontSize: 12, fontWeight: 600,
                    }}
                >
                    <ThumbsUp size={13} /> {s.upvotes}
                </button>
                <button
                    onClick={() => onVote(s.id, 'downvote')}
                    disabled={voted}
                    title="Not helpful"
                    style={{
                        display: 'flex', alignItems: 'center', gap: 4, padding: '8px 12px',
                        borderRadius: 10, border: '1px solid #E2E8F0', background: voted ? '#F8FAFC' : '#fff',
                        color: voted ? '#CBD5E1' : '#94A3B8', cursor: voted ? 'default' : 'pointer', fontSize: 12, fontWeight: 600,
                    }}
                >
                    <ThumbsDown size={13} /> {s.downvotes}
                </button>

                <button
                    onClick={() => onDismiss(s.id)}
                    title="Dismiss"
                    style={{
                        display: 'flex', alignItems: 'center', padding: 8, borderRadius: 10,
                        border: '1px solid #E2E8F0', background: '#fff',
                        color: '#94A3B8', cursor: 'pointer', transition: 'all 0.15s',
                    }}
                >
                    <X size={14} />
                </button>
            </div>
        </div>
    );
}
