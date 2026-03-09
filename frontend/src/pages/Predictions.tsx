// frontend/src/pages/Predictions.tsx
import { useState, useEffect, useCallback } from 'react';
import {
    TrendingUp, Activity, Search, RefreshCw,
    AlertTriangle, X, Zap, CheckCircle, Info, Code2,
    ChevronDown, ChevronRight, BellOff, GitBranch, Layers
} from 'lucide-react';
import { LineChart, Line, ResponsiveContainer, Tooltip } from 'recharts';
import { useProject } from '../context/ProjectContext';
import api from '../services/api';

// ── Types ─────────────────────────────────────────────────────────────────────

interface Prediction {
    id: string;
    repo_id: string | null;
    repo_name: string;
    repo_owner: string;
    repo_language: string;
    repo_is_default: boolean;
    service_name: string;
    prediction_type: string;
    description: string;
    confidence: number;
    severity: string;
    estimated_impact_time: string | null;
    time_until_impact: string;
    status: string;
    created_at: string;
    // local-only fields from the old mock system
    _snoozed?: boolean;
    _fading?: boolean;
}

interface CodeChange {
    file: string;
    issue: string;
    before: string;
    after: string;
    impact: 'Critical' | 'High' | 'Medium' | 'Low';
}

// ── Constants ──────────────────────────────────────────────────────────────────

const SEVERITY_COLOR: Record<string, string> = {
    P1: '#EF4444', P2: '#F97316', P3: '#F59E0B', P4: '#6366F1',
};

const SEVERITY_LABELS: Record<string, string> = {
    P1: 'Critical', P2: 'High', P3: 'Medium', P4: 'Low',
};

const IMPACT_COLOR: Record<string, string> = {
    Critical: '#EF4444', High: '#F97316', Medium: '#F59E0B', Low: '#10B981',
};

const IMPACT_BG: Record<string, string> = {
    Critical: '#FEF2F2', High: '#FFF7ED', Medium: '#FFFBEB', Low: '#F0FDF4',
};

const PREDICTION_TYPE_LABELS: Record<string, string> = {
    cpu_spike: 'CPU Usage',
    memory_exhaustion: 'Memory Usage',
    high_error_rate: 'Error Rate',
    latency_spike: 'Latency',
    disk_saturation: 'Disk I/O',
    network_saturation: 'Network',
    connection_pool_exhaustion: 'DB Connections',
    queue_lag: 'Queue Lag',
};

const LANGUAGE_COLORS: Record<string, string> = {
    Python: 'bg-blue-50 text-blue-600',
    JavaScript: 'bg-yellow-50 text-yellow-700',
    TypeScript: 'bg-blue-50 text-blue-700',
    Java: 'bg-orange-50 text-orange-600',
    Go: 'bg-cyan-50 text-cyan-600',
    Ruby: 'bg-red-50 text-red-600',
    Rust: 'bg-orange-50 text-orange-700',
};

// ── Investigate Modal ──────────────────────────────────────────────────────────

function InvestigateModal({
    pred, onClose,
}: {
    pred: Prediction;
    onClose: () => void;
}) {
    const [step, setStep] = useState(0);
    const steps = ['Analyzing metrics…', 'Scanning codebase…', 'Generating recommendations…', 'Done'];
    const done = step >= steps.length - 1;

    // Auto-progress
    useState(() => {
        const id = setInterval(() => {
            setStep(s => {
                if (s >= steps.length - 1) { clearInterval(id); return s; }
                return s + 1;
            });
        }, 700);
        return () => clearInterval(id);
    });

    const mockChanges: CodeChange[] = [
        {
            file: `src/${pred.prediction_type.replace(/_/g, '/')}/handler.py`,
            issue: `${PREDICTION_TYPE_LABELS[pred.prediction_type] || pred.prediction_type} threshold exceeded — needs tuning`,
            before: `# Default config\nthreshold = None`,
            after: `# Tuned config\nthreshold = 0.85  # Evidence-based limit`,
            impact: pred.confidence >= 0.90 ? 'Critical' : pred.confidence >= 0.75 ? 'High' : 'Medium',
        },
    ];

    return (
        <div style={{
            position: 'fixed', inset: 0, zIndex: 1000,
            background: 'rgba(15,23,42,0.6)', backdropFilter: 'blur(4px)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24,
        }} onClick={onClose}>
            <div style={{
                background: '#fff', borderRadius: 20, width: '100%', maxWidth: 680,
                maxHeight: '88vh', overflow: 'hidden', display: 'flex', flexDirection: 'column',
                boxShadow: '0 24px 64px rgba(0,0,0,0.18)',
            }} onClick={e => e.stopPropagation()}>

                {/* Header */}
                <div style={{
                    padding: '20px 24px', borderBottom: '1px solid #E2E8F0',
                    display: 'flex', alignItems: 'center', gap: 14, flexShrink: 0,
                }}>
                    <div style={{
                        width: 40, height: 40, borderRadius: 12,
                        background: `${SEVERITY_COLOR[pred.severity]}15`,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}>
                        <Zap size={18} color={SEVERITY_COLOR[pred.severity]} />
                    </div>
                    <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 700, fontSize: 15, color: '#0F172A' }}>
                            Investigation Report
                        </div>
                        <div style={{ fontSize: 12, color: '#64748B' }}>
                            {pred.repo_owner}/{pred.repo_name} · {PREDICTION_TYPE_LABELS[pred.prediction_type] || pred.prediction_type}
                        </div>
                    </div>
                    <span style={{
                        fontSize: 11, fontWeight: 700, padding: '4px 10px', borderRadius: 8,
                        background: `${SEVERITY_COLOR[pred.severity]}15`, color: SEVERITY_COLOR[pred.severity],
                    }}>{pred.severity}</span>
                    <button onClick={onClose} style={{
                        background: '#F1F5F9', border: 'none', borderRadius: 8,
                        padding: 7, cursor: 'pointer', display: 'flex',
                    }}>
                        <X size={15} color="#64748B" />
                    </button>
                </div>

                {/* Progress */}
                {!done && (
                    <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 14 }}>
                        {steps.slice(0, -1).map((s, i) => (
                            <div key={s} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                                <div style={{
                                    width: 28, height: 28, borderRadius: '50%', flexShrink: 0,
                                    background: step > i ? '#10B981' : step === i ? '#6366F1' : '#F1F5F9',
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    transition: 'all 0.3s',
                                }}>
                                    {step > i
                                        ? <CheckCircle size={14} color="#fff" />
                                        : step === i
                                            ? <div style={{ width: 10, height: 10, borderRadius: '50%', border: '2px solid #fff', borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite' }} />
                                            : <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#CBD5E1' }} />}
                                </div>
                                <span style={{
                                    fontSize: 13, color: step >= i ? '#0F172A' : '#94A3B8',
                                    fontWeight: step === i ? 600 : 400,
                                }}>{s}</span>
                            </div>
                        ))}
                    </div>
                )}

                {/* Report */}
                {done && (
                    <div style={{ overflowY: 'auto', padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 20 }}>
                        <div style={{ background: '#FFF7ED', border: '1px solid #FED7AA', borderRadius: 12, padding: '16px 18px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                                <Info size={15} color="#EA580C" />
                                <span style={{ fontSize: 12, fontWeight: 700, color: '#EA580C', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Root Cause</span>
                            </div>
                            <div style={{ fontSize: 13, color: '#7C2D12', lineHeight: 1.7 }}>
                                {pred.description}
                            </div>
                        </div>

                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
                            {[
                                { label: 'Impact Level', value: SEVERITY_LABELS[pred.severity] || 'Medium', colored: true },
                                { label: 'Confidence', value: `${Math.round(pred.confidence * 100)}%`, colored: false },
                                { label: 'Time to Impact', value: pred.time_until_impact, colored: false },
                            ].map(stat => (
                                <div key={stat.label} style={{
                                    background: stat.colored ? IMPACT_BG[stat.value] || '#FFF7ED' : '#F8FAFC',
                                    borderRadius: 10, padding: '12px 16px',
                                    border: stat.colored ? `1px solid ${IMPACT_COLOR[stat.value] || '#F97316'}30` : '1px solid #E2E8F0',
                                }}>
                                    <div style={{ fontSize: 10, fontWeight: 600, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>{stat.label}</div>
                                    <div style={{ fontSize: 18, fontWeight: 800, color: stat.colored ? (IMPACT_COLOR[stat.value] || '#F97316') : '#0F172A' }}>{stat.value}</div>
                                </div>
                            ))}
                        </div>

                        <div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                                <Code2 size={15} color="#6366F1" />
                                <span style={{ fontSize: 14, fontWeight: 700, color: '#0F172A' }}>
                                    Recommended Code Changes ({mockChanges.length})
                                </span>
                            </div>
                            {mockChanges.map((change, i) => (
                                <div key={i} style={{
                                    border: '1px solid #E2E8F0', borderRadius: 12, overflow: 'hidden',
                                    borderLeft: `3px solid ${IMPACT_COLOR[change.impact]}`,
                                }}>
                                    <div style={{
                                        padding: '10px 14px', background: '#F8FAFC',
                                        borderBottom: '1px solid #E2E8F0',
                                        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                    }}>
                                        <code style={{ fontSize: 11, color: '#374151', fontWeight: 600 }}>{change.file}</code>
                                        <span style={{
                                            fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 6,
                                            background: IMPACT_BG[change.impact], color: IMPACT_COLOR[change.impact],
                                        }}>{change.impact}</span>
                                    </div>
                                    <div style={{ padding: '10px 14px', fontSize: 12, color: '#374151', borderBottom: '1px solid #F1F5F9' }}>
                                        ⚠️ {change.issue}
                                    </div>
                                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0 }}>
                                        <div style={{ padding: '10px 14px', borderRight: '1px solid #F1F5F9' }}>
                                            <div style={{ fontSize: 10, fontWeight: 700, color: '#DC2626', marginBottom: 6 }}>BEFORE</div>
                                            <pre style={{ margin: 0, fontSize: 11, background: '#FEF2F2', borderRadius: 6, padding: '8px 10px', color: '#7F1D1D', overflow: 'auto', fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>{change.before}</pre>
                                        </div>
                                        <div style={{ padding: '10px 14px' }}>
                                            <div style={{ fontSize: 10, fontWeight: 700, color: '#059669', marginBottom: 6 }}>AFTER</div>
                                            <pre style={{ margin: 0, fontSize: 11, background: '#ECFDF5', borderRadius: 6, padding: '8px 10px', color: '#064E3B', overflow: 'auto', fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>{change.after}</pre>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {done && (
                    <div style={{
                        padding: '14px 24px', borderTop: '1px solid #E2E8F0',
                        display: 'flex', justifyContent: 'flex-end', gap: 10, flexShrink: 0,
                    }}>
                        <button onClick={onClose} style={{
                            padding: '8px 18px', borderRadius: 9, fontSize: 13,
                            border: '1px solid #E2E8F0', background: '#fff',
                            cursor: 'pointer', color: '#374151', fontWeight: 600,
                        }}>Close</button>
                    </div>
                )}
            </div>
        </div>
    );
}

// ── Prediction Card ────────────────────────────────────────────────────────────

function PredictionCard({
    prediction,
    onInvestigate,
    onSnooze,
    fading,
}: {
    prediction: Prediction;
    onInvestigate: () => void;
    onSnooze: () => void;
    fading: boolean;
}) {
    const sev = prediction.severity as keyof typeof SEVERITY_COLOR;
    const langColorClass = LANGUAGE_COLORS[prediction.repo_language] || 'bg-gray-50 text-gray-600';
    const typeLabel = PREDICTION_TYPE_LABELS[prediction.prediction_type]
        || prediction.prediction_type.replace(/_/g, ' ');

    const borderColor = SEVERITY_COLOR[sev] || '#6366F1';
    const badgeBg = sev === 'P1' ? '#FEF2F2' : sev === 'P2' ? '#FFF7ED' : sev === 'P3' ? '#FFFBEB' : '#EEF2FF';
    const badgeColor = SEVERITY_COLOR[sev] || '#6366F1';

    return (
        <div style={{
            background: '#fff',
            borderRadius: 14,
            border: '1px solid #E2E8F0',
            borderLeft: `4px solid ${borderColor}`,
            padding: '18px 22px',
            boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
            transition: 'opacity 0.4s ease, transform 0.4s ease',
            opacity: fading ? 0 : 1,
            transform: fading ? 'translateX(30px)' : 'none',
        }}>
            {/* Header row */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 4 }}>
                <span style={{
                    fontSize: 11, fontWeight: 800, padding: '2px 8px', borderRadius: 6,
                    background: badgeBg, color: badgeColor,
                }}>{sev}</span>
                <span style={{ fontWeight: 700, fontSize: 15, color: '#0F172A' }}>
                    {prediction.repo_name}
                </span>
                <span style={{
                    fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 9999,
                    background: '#F1F5F9', color: '#64748B',
                }}>{prediction.repo_language}</span>
                <span style={{ color: '#CBD5E1', fontSize: 13 }}>·</span>
                <span style={{ fontSize: 12, color: '#64748B' }}>{typeLabel}</span>

                <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{
                        fontSize: 11, background: '#EEF2FF', color: '#6366F1',
                        padding: '2px 8px', borderRadius: 9999, fontWeight: 600,
                    }}>{Math.round(prediction.confidence * 100)}% confidence</span>
                    <span style={{
                        fontSize: 11, background: '#F8FAFC', color: '#64748B',
                        padding: '2px 8px', borderRadius: 9999, display: 'flex', alignItems: 'center', gap: 4,
                    }}>
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
                        </svg>
                        {prediction.time_until_impact}
                    </span>
                    <span style={{
                        fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 6,
                        background: badgeBg, color: badgeColor,
                    }}>{SEVERITY_LABELS[sev] || sev}</span>
                </div>
            </div>

            {/* Repo path */}
            <div style={{
                display: 'flex', alignItems: 'center', gap: 4,
                fontSize: 11, color: '#94A3B8', fontFamily: 'monospace', marginBottom: 10,
            }}>
                <GitBranch size={10} />
                {prediction.repo_owner}/{prediction.repo_name}
                {prediction.repo_is_default && (
                    <span style={{
                        marginLeft: 6, fontSize: 10, background: '#F8FAFC', color: '#94A3B8',
                        padding: '1px 6px', borderRadius: 4, fontFamily: 'sans-serif',
                    }}>default</span>
                )}
            </div>

            {/* Description */}
            <p style={{ fontSize: 13, color: '#334155', lineHeight: 1.7, margin: '0 0 14px' }}>
                {prediction.description}
            </p>

            {/* Actions */}
            <div style={{ display: 'flex', gap: 8 }}>
                <button
                    onClick={onInvestigate}
                    style={{
                        display: 'flex', alignItems: 'center', gap: 6,
                        padding: '7px 14px', borderRadius: 9, fontSize: 12,
                        border: 'none',
                        background: 'linear-gradient(135deg, #6366F1, #4F46E5)',
                        color: '#fff', fontWeight: 600, cursor: 'pointer',
                    }}
                >
                    <AlertTriangle size={12} /> Investigate
                </button>
                <button
                    onClick={onSnooze}
                    style={{
                        display: 'flex', alignItems: 'center', gap: 6,
                        padding: '7px 14px', borderRadius: 9, fontSize: 12,
                        background: '#F1F5F9', color: '#374151', fontWeight: 600,
                        border: 'none', cursor: 'pointer',
                    }}
                >
                    <BellOff size={12} /> Snooze
                </button>
            </div>
        </div>
    );
}

// ── Group by Repository section ────────────────────────────────────────────────

function RepoGroup({ repoName, repoOwner, predictions, onInvestigate, onSnooze, fadingIds }: {
    repoName: string;
    repoOwner: string;
    predictions: Prediction[];
    onInvestigate: (p: Prediction) => void;
    onSnooze: (id: string) => void;
    fadingIds: Set<string>;
}) {
    const [collapsed, setCollapsed] = useState(false);
    const maxSev = predictions.reduce((acc, p) => {
        const order: Record<string, number> = { P1: 0, P2: 1, P3: 2, P4: 3 };
        return (order[p.severity] ?? 3) < (order[acc] ?? 3) ? p.severity : acc;
    }, 'P4');
    const dotColor = SEVERITY_COLOR[maxSev] || '#6366F1';

    return (
        <div style={{ marginBottom: 8 }}>
            <button
                onClick={() => setCollapsed(c => !c)}
                style={{
                    width: '100%', display: 'flex', alignItems: 'center', gap: 10,
                    background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: 12,
                    padding: '12px 18px', cursor: 'pointer', marginBottom: collapsed ? 0 : 8,
                }}
            >
                <div style={{ width: 10, height: 10, borderRadius: '50%', background: dotColor, flexShrink: 0 }} />
                <span style={{ fontWeight: 700, fontSize: 14, color: '#0F172A' }}>{repoName}</span>
                <span style={{ fontSize: 11, color: '#94A3B8', fontFamily: 'monospace' }}>{repoOwner}/{repoName}</span>
                <span style={{
                    marginLeft: 4, fontSize: 11, background: '#E0E7FF', color: '#4338CA',
                    padding: '1px 8px', borderRadius: 9999, fontWeight: 700,
                }}>{predictions.length}</span>
                <div style={{ marginLeft: 'auto' }}>
                    {collapsed ? <ChevronRight size={16} color="#94A3B8" /> : <ChevronDown size={16} color="#94A3B8" />}
                </div>
            </button>
            {!collapsed && (
                <div style={{ paddingLeft: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {predictions.map(p => (
                        <PredictionCard
                            key={p.id}
                            prediction={p}
                            onInvestigate={() => onInvestigate(p)}
                            onSnooze={() => onSnooze(p.id)}
                            fading={fadingIds.has(p.id)}
                        />
                    ))}
                </div>
            )}
        </div>
    );
}

// ── Main Predictions Page ──────────────────────────────────────────────────────

export default function Predictions() {
    const { selectedProject } = useProject();
    const [predictions, setPredictions] = useState<Prediction[]>([]);
    const [searchText, setSearchText] = useState('');
    const [filterSev, setFilterSev] = useState('');
    const [loading, setLoading] = useState(false);
    const [investigating, setInvestigating] = useState<Prediction | null>(null);
    const [groupByRepo, setGroupByRepo] = useState(false);
    const [fadingIds, setFadingIds] = useState<Set<string>>(new Set());

    const fetchPredictions = useCallback(async () => {
        setLoading(true);
        try {
            const qs = selectedProject ? `?project_id=${selectedProject.id}` : '';
            const data = await api.get<{ predictions: Prediction[]; total: number }>(`/predictions${qs}`);
            setPredictions(data.predictions || []);
        } catch {
            // API unavailable — keep existing list
        } finally {
            setLoading(false);
        }
    }, [selectedProject?.id]);

    useEffect(() => {
        fetchPredictions();
    }, [fetchPredictions]);

    const handleSnooze = async (id: string) => {
        // Fade out animation first
        setFadingIds(prev => new Set(prev).add(id));
        setTimeout(async () => {
            try {
                await api.post(`/predictions/${id}/snooze`, {});
            } catch { /* fire and forget — optimistic UI */ }
            setPredictions(prev => prev.filter(p => p.id !== id));
            setFadingIds(prev => {
                const next = new Set(prev);
                next.delete(id);
                return next;
            });
        }, 400);
    };

    const visible = predictions.filter(p =>
        !fadingIds.has(p.id) &&
        (!filterSev || p.severity === filterSev) &&
        (!searchText
            || p.repo_name.toLowerCase().includes(searchText.toLowerCase())
            || p.repo_owner.toLowerCase().includes(searchText.toLowerCase())
            || p.description.toLowerCase().includes(searchText.toLowerCase()))
    );

    // Severity counts for stats row
    const bySev = { P1: 0, P2: 0, P3: 0, P4: 0 };
    visible.forEach(p => { if (p.severity in bySev) bySev[p.severity as keyof typeof bySev]++; });

    // Group by repo
    const grouped: Record<string, Prediction[]> = {};
    visible.forEach(p => {
        const key = `${p.repo_owner}/${p.repo_name}`;
        if (!grouped[key]) grouped[key] = [];
        grouped[key].push(p);
    });

    const subtitleText = selectedProject
        ? `Showing predictions for ${selectedProject.owner}/${selectedProject.name}`
        : 'ML-powered failure forecasts';

    return (
        <div className="animate-fade" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {investigating && (
                <InvestigateModal pred={investigating} onClose={() => setInvestigating(null)} />
            )}

            {/* Page header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                    <h1 style={{ fontSize: 22, fontWeight: 800, color: '#0F172A', letterSpacing: '-0.02em' }}>
                        Predictions
                    </h1>
                    <div style={{ fontSize: 13, color: '#64748B', marginTop: 3 }}>
                        {selectedProject
                            ? <><span style={{ color: '#6366F1', fontWeight: 600 }}>{selectedProject.owner}/{selectedProject.name}</span> · {subtitleText}</>
                            : subtitleText}
                        {' · '}{visible.length} active prediction{visible.length !== 1 ? 's' : ''}
                    </div>
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    {/* Search */}
                    <div style={{ position: 'relative' }}>
                        <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: '#94A3B8' }} />
                        <input
                            className="form-input"
                            value={searchText}
                            onChange={e => setSearchText(e.target.value)}
                            placeholder="Search repo…"
                            style={{ paddingLeft: 32, width: 180 }}
                        />
                    </div>
                    {/* Severity filter */}
                    <select className="form-select" value={filterSev} onChange={e => setFilterSev(e.target.value)}>
                        {['', 'P1', 'P2', 'P3', 'P4'].map(s => (
                            <option key={s} value={s}>{s || 'All Severities'}</option>
                        ))}
                    </select>
                    {/* Group toggle */}
                    <button
                        onClick={() => setGroupByRepo(g => !g)}
                        style={{
                            display: 'flex', alignItems: 'center', gap: 6,
                            padding: '7px 13px', borderRadius: 9, fontSize: 12, fontWeight: 600,
                            background: groupByRepo ? '#EEF2FF' : '#F8FAFC',
                            color: groupByRepo ? '#4F46E5' : '#374151',
                            border: `1px solid ${groupByRepo ? '#C7D2FE' : '#E2E8F0'}`,
                            cursor: 'pointer',
                        }}
                    >
                        <Layers size={13} /> Group by Repository
                    </button>
                    {/* Refresh */}
                    <button className="btn btn-secondary" onClick={fetchPredictions} disabled={loading}>
                        <RefreshCw size={13} style={loading ? { animation: 'spin 1s linear infinite' } : {}} />
                    </button>
                </div>
            </div>

            {/* Severity summary cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
                {([
                    { label: 'Critical (P1)', count: bySev.P1, color: '#EF4444' },
                    { label: 'High (P2)', count: bySev.P2, color: '#F97316' },
                    { label: 'Medium (P3)', count: bySev.P3, color: '#F59E0B' },
                    { label: 'Low (P4)', count: bySev.P4, color: '#6366F1' },
                ] as const).map(s => (
                    <div key={s.label} className="card" style={{ padding: '16px 20px' }}>
                        <div style={{ fontSize: 11, fontWeight: 600, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{s.label}</div>
                        <div style={{ fontSize: 28, fontWeight: 800, color: s.count > 0 ? s.color : '#0F172A', marginTop: 6, letterSpacing: '-0.02em' }}>{s.count}</div>
                    </div>
                ))}
            </div>

            {/* Prediction list / grouped view */}
            {loading ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {[1, 2, 3].map(i => <div key={i} className="skeleton" style={{ height: 140, borderRadius: 14 }} />)}
                </div>
            ) : groupByRepo ? (
                <div>
                    {Object.entries(grouped).map(([key, preds]) => {
                        const [owner, ...nameParts] = key.split('/');
                        const name = nameParts.join('/');
                        return (
                            <RepoGroup
                                key={key}
                                repoName={name}
                                repoOwner={owner}
                                predictions={preds}
                                onInvestigate={setInvestigating}
                                onSnooze={handleSnooze}
                                fadingIds={fadingIds}
                            />
                        );
                    })}
                    {Object.keys(grouped).length === 0 && (
                        <div className="card">
                            <div className="empty-state">
                                <div className="empty-state-icon"><Activity size={22} color="#94A3B8" /></div>
                                <div style={{ fontSize: 14, color: '#64748B' }}>No active predictions</div>
                            </div>
                        </div>
                    )}
                </div>
            ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {visible.map(pred => (
                        <PredictionCard
                            key={pred.id}
                            prediction={pred}
                            onInvestigate={() => setInvestigating(pred)}
                            onSnooze={() => handleSnooze(pred.id)}
                            fading={fadingIds.has(pred.id)}
                        />
                    ))}
                    {visible.length === 0 && (
                        <div className="card">
                            <div className="empty-state">
                                <div className="empty-state-icon"><Activity size={22} color="#94A3B8" /></div>
                                <div style={{ fontSize: 14, color: '#64748B' }}>No active predictions</div>
                                <div style={{ fontSize: 12, color: '#94A3B8', marginTop: 4 }}>All monitored repositories look healthy</div>
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
