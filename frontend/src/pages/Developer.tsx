import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
    Code2, FileText, AlertTriangle, CheckCircle, RefreshCw, ChevronRight,
    ChevronDown, ThumbsUp, ThumbsDown, Loader2, GitBranch, Package,
    Activity, Star, ExternalLink, Info, Zap
} from 'lucide-react';
import api from '../services/api';
import { useProject } from '../context/ProjectContext';

interface FileTreeItem {
    path: string;
    name: string;
    type: 'file' | 'dir';
    size?: number;
    loc?: number;
    risk?: number;
    issues?: number;
}

interface Issue {
    // MongoDB fields (_id serialized as error_id)
    error_id?: string;
    issue_id?: string;          // legacy in-memory field
    file_path?: string;         // MongoDB field
    file?: string;              // legacy field
    line_number: number;
    error_type?: string;        // MongoDB field
    issue_type?: string;        // legacy field
    language?: string;
    severity: 'P1' | 'P2' | 'P3' | 'P4';
    title?: string;
    description: string;
    suggestion: string;
    code_before?: string;
    code_after?: string;
    source?: string;
    confidence_score?: number;
    upvotes?: number;
    downvotes?: number;
    resolved?: boolean;
    feedback?: { upvotes: number; downvotes: number };
}

function getIssueId(issue: Issue): string {
    return issue.error_id || issue.issue_id || `${issue.file || issue.file_path}:${issue.line_number}`;
}
function getFilePath(issue: Issue): string {
    return issue.file_path || issue.file || '?';
}
function getErrorType(issue: Issue): string {
    return issue.error_type || issue.issue_type || 'unknown';
}

const SEV_COLOR: Record<string, string> = { P1: '#EF4444', P2: '#F97316', P3: '#F59E0B', P4: '#6366F1' };
const ISSUE_TYPE_LABELS: Record<string, string> = {
    missing_error_handling: 'Missing Error Handling',
    security_vulnerability: 'Security Vulnerability',
    performance_issue: 'Performance Issue',
    null_pointer_risk: 'Null Pointer Risk',
    resource_leak: 'Resource Leak',
    hardcoded_secret: 'Hardcoded Secret',
    missing_input_validation: 'Missing Validation',
    deprecated_usage: 'Deprecated Usage',
};

function IssueCard({ issue, repoId, onFeedback, onResolve }: {
    issue: Issue; repoId: string;
    onFeedback: (issueId: string, type: 'upvote' | 'downvote') => void;
    onResolve: (issueId: string) => void;
}) {
    const [expanded, setExpanded] = useState(false);
    const [voted, setVoted] = useState<'upvote' | 'downvote' | null>(null);
    const [voting, setVoting] = useState('');
    const [resolving, setResolving] = useState(false);
    const [resolved, setResolved] = useState(issue.resolved || false);

    // Derive counts from MongoDB fields or legacy feedback field
    const upvotes = (issue.upvotes ?? issue.feedback?.upvotes) || 0;
    const downvotes = (issue.downvotes ?? issue.feedback?.downvotes) || 0;
    const issueId = getIssueId(issue);
    const filePath = getFilePath(issue);
    const errorType = getErrorType(issue);
    const confidence = issue.confidence_score;

    const vote = async (type: 'upvote' | 'downvote') => {
        if (voted) return; // already voted
        setVoting(type);
        try {
            // Try MongoDB endpoint first, fall back to legacy
            const result = await api.submitErrorFeedback(repoId, issueId, type)
                .catch(() => api.submitIssueFeedback(repoId, issueId, type));
            setVoted(type);
            onFeedback(issueId, type);
        } finally {
            setVoting('');
        }
    };

    const handleResolve = async () => {
        setResolving(true);
        try {
            await api.resolveError(repoId, issueId);
            setResolved(true);
            onResolve(issueId);
        } finally {
            setResolving(false);
        }
    };

    if (resolved) return null; // hide resolved issues

    return (
        <div style={{
            borderRadius: 10, border: '1px solid #E2E8F0',
            background: '#FAFAFA', overflow: 'hidden',
            borderLeft: `3px solid ${SEV_COLOR[issue.severity] || '#94A3B8'}`,
        }}>
            <div style={{ padding: '12px 16px', display: 'flex', alignItems: 'flex-start', gap: 12, cursor: 'pointer' }}
                onClick={() => setExpanded(v => !v)}>
                <span style={{
                    fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 5,
                    background: `${SEV_COLOR[issue.severity]}18`,
                    color: SEV_COLOR[issue.severity],
                    flexShrink: 0,
                }}>
                    {issue.severity}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: '#0F172A', marginBottom: 2 }}>
                        {issue.title || ISSUE_TYPE_LABELS[errorType] || errorType}
                    </div>
                    <div style={{ fontSize: 11, color: '#64748B', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {filePath}:{issue.line_number}
                        {issue.language && <span style={{ color: '#CBD5E1', marginLeft: 6 }}>· {issue.language}</span>}
                    </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    {confidence !== undefined && (
                        <div title={`Confidence: ${Math.round(confidence * 100)}%`} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            <div style={{ width: 40, height: 4, background: '#E2E8F0', borderRadius: 2 }}>
                                <div style={{
                                    height: '100%',
                                    width: `${Math.round(confidence * 100)}%`,
                                    background: confidence > 0.7 ? '#10B981' : confidence > 0.4 ? '#F59E0B' : '#EF4444',
                                    borderRadius: 2,
                                }} />
                            </div>
                            <span style={{ fontSize: 10, color: '#94A3B8' }}>{Math.round(confidence * 100)}%</span>
                        </div>
                    )}
                    {issue.source && (
                        <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 4, background: '#F1F5F9', color: '#64748B' }}>
                            {issue.source === 'phi3' ? 'Phi-3' : 'Static'}
                        </span>
                    )}
                    {expanded ? <ChevronDown size={14} color="#94A3B8" /> : <ChevronRight size={14} color="#94A3B8" />}
                </div>
            </div>

            {expanded && (
                <div style={{ borderTop: '1px solid #E2E8F0', padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
                    <div style={{ fontSize: 13, color: '#374151' }}>{issue.description}</div>
                    <div style={{ background: '#F0FDF4', border: '1px solid #BBF7D0', borderRadius: 8, padding: '10px 14px' }}>
                        <div style={{ fontSize: 11, fontWeight: 600, color: '#166534', marginBottom: 4 }}>SUGGESTION</div>
                        <div style={{ fontSize: 12, color: '#166534' }}>{issue.suggestion}</div>
                    </div>

                    {(issue.code_before || issue.code_after) && (
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                            {issue.code_before && (
                                <div>
                                    <div style={{ fontSize: 10, fontWeight: 700, color: '#DC2626', marginBottom: 4, textTransform: 'uppercase' }}>Before</div>
                                    <pre style={{
                                        background: '#FEF2F2', border: '1px solid #FECACA', borderRadius: 6,
                                        padding: '8px 12px', fontSize: 11, color: '#7F1D1D',
                                        margin: 0, overflow: 'auto', fontFamily: 'monospace',
                                        whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                                    }}>{issue.code_before}</pre>
                                </div>
                            )}
                            {issue.code_after && (
                                <div>
                                    <div style={{ fontSize: 10, fontWeight: 700, color: '#059669', marginBottom: 4, textTransform: 'uppercase' }}>After</div>
                                    <pre style={{
                                        background: '#ECFDF5', border: '1px solid #A7F3D0', borderRadius: 6,
                                        padding: '8px 12px', fontSize: 11, color: '#064E3B',
                                        margin: 0, overflow: 'auto', fontFamily: 'monospace',
                                        whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                                    }}>{issue.code_after}</pre>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Upvote/Downvote + Resolve */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 4 }}>
                        <span style={{ fontSize: 11, color: '#94A3B8', flex: 1 }}>
                            {voted ? (voted === 'upvote' ? '👍 Thanks for the feedback!' : '👎 We\'ll improve this.') : 'Was this helpful?'}
                        </span>
                        <button
                            onClick={e => { e.stopPropagation(); vote('upvote'); }}
                            disabled={!!voting || !!voted}
                            style={{
                                display: 'flex', alignItems: 'center', gap: 5, padding: '5px 10px',
                                border: `1px solid ${voted === 'upvote' ? '#10B981' : '#E2E8F0'}`,
                                borderRadius: 7, background: voted === 'upvote' ? '#ECFDF5' : '#fff',
                                cursor: voted ? 'default' : 'pointer', fontSize: 12,
                                color: voted === 'upvote' ? '#059669' : '#64748B', fontWeight: 600,
                                opacity: !!voted && voted !== 'upvote' ? 0.4 : 1,
                            }}>
                            {voting === 'upvote' ? <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} /> : <ThumbsUp size={12} />}
                            {upvotes + (voted === 'upvote' ? 1 : 0)}
                        </button>
                        <button
                            onClick={e => { e.stopPropagation(); vote('downvote'); }}
                            disabled={!!voting || !!voted}
                            style={{
                                display: 'flex', alignItems: 'center', gap: 5, padding: '5px 10px',
                                border: `1px solid ${voted === 'downvote' ? '#EF4444' : '#E2E8F0'}`,
                                borderRadius: 7, background: voted === 'downvote' ? '#FEF2F2' : '#fff',
                                cursor: voted ? 'default' : 'pointer', fontSize: 12,
                                color: voted === 'downvote' ? '#DC2626' : '#64748B', fontWeight: 600,
                                opacity: !!voted && voted !== 'downvote' ? 0.4 : 1,
                            }}>
                            {voting === 'downvote' ? <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} /> : <ThumbsDown size={12} />}
                            {downvotes + (voted === 'downvote' ? 1 : 0)}
                        </button>
                        <button
                            onClick={e => { e.stopPropagation(); handleResolve(); }}
                            disabled={resolving}
                            style={{
                                display: 'flex', alignItems: 'center', gap: 4, padding: '5px 10px',
                                border: '1px solid #C7D2FE', borderRadius: 7, background: '#EEF2FF',
                                cursor: 'pointer', fontSize: 12, color: '#6366F1', fontWeight: 600,
                            }}>
                            {resolving ? <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} /> : <CheckCircle size={12} />}
                            Mark Resolved
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}

function StatCard({ label, value, sub, color }: { label: string; value: any; sub?: string; color?: string }) {
    return (
        <div style={{ background: '#F8FAFC', borderRadius: 10, padding: '14px 16px' }}>
            <div style={{ fontSize: 10, color: '#94A3B8', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>{label}</div>
            <div style={{ fontSize: 22, fontWeight: 800, color: color || '#0F172A', lineHeight: 1 }}>{value}</div>
            {sub && <div style={{ fontSize: 11, color: '#64748B', marginTop: 4 }}>{sub}</div>}
        </div>
    );
}

const DEMO_FILES = [
    { name: 'api/routes.py', loc: 342, issues: 3, risk: 0.82 },
    { name: 'core/engine.py', loc: 891, issues: 5, risk: 0.91 },
    { name: 'models/predictor.py', loc: 214, issues: 1, risk: 0.45 },
    { name: 'utils/cache.py', loc: 128, issues: 2, risk: 0.67 },
    { name: 'db/repository.py', loc: 476, issues: 4, risk: 0.88 },
];

const DEMO_SUGGESTIONS = [
    { severity: 'P1', impact: 'Critical', file: 'core/engine.py', line: 147, title: 'Unbounded memory growth in event loop', description: 'Events are appended to a list that is never cleared. Under sustained load this will exhaust heap memory.', before: 'self.events.append(event)', after: 'self.events = self.events[-1000:]  # keep last 1000\nself.events.append(event)' },
    { severity: 'P1', impact: 'Critical', file: 'db/repository.py', line: 83, title: 'SQL injection vulnerability', description: 'User input is directly interpolated into the query string without parameterization.', before: `query = f"SELECT * FROM users WHERE id = {user_id}"`, after: `query = "SELECT * FROM users WHERE id = %s"\ncursor.execute(query, (user_id,))` },
    { severity: 'P2', impact: 'High', file: 'api/routes.py', line: 61, title: 'Missing authentication on admin endpoint', description: '/admin/reset has no auth guard — any user can trigger a full data reset.', before: `@app.route('/admin/reset')\ndef reset(): clear_all()`, after: `@app.route('/admin/reset')\n@require_auth(role='admin')\ndef reset(): clear_all()` },
    { severity: 'P2', impact: 'High', file: 'utils/cache.py', line: 34, title: 'Cache never expires — stale data risk', description: 'Cache entries are written without TTL, causing stale reads indefinitely.', before: `cache.set(key, value)`, after: `cache.set(key, value, ttl=300)  # 5 min TTL` },
    { severity: 'P3', impact: 'Medium', file: 'models/predictor.py', line: 108, title: 'Model loaded synchronously on each request', description: 'Loading the ML model inside the request handler adds 200–400ms latency per call.', before: `def predict(data):\n    model = joblib.load('model.pkl')\n    return model.predict(data)`, after: `_MODEL = joblib.load('model.pkl')  # load once\n\ndef predict(data):\n    return _MODEL.predict(data)` },
];

const SEV_C: Record<string, string> = { P1: '#EF4444', P2: '#F97316', P3: '#F59E0B', P4: '#6366F1' };
const SEV_BG: Record<string, string> = { P1: '#FEF2F2', P2: '#FFF7ED', P3: '#FFFBEB', P4: '#EEF2FF' };

function DeveloperDemo() {
    const [analyzing, setAnalyzing] = useState(false);
    const [progress, setProgress] = useState(0);
    const [done, setDone] = useState(false);
    const [expanded, setExpanded] = useState<number | null>(null);

    const runAnalysis = () => {
        setAnalyzing(true);
        setProgress(0);
        setDone(false);
        const interval = setInterval(() => {
            setProgress(p => {
                if (p >= 100) {
                    clearInterval(interval);
                    setAnalyzing(false);
                    setDone(true);
                    return 100;
                }
                return p + Math.random() * 12;
            });
        }, 180);
    };

    return (
        <div className="animate-fade" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                    <h1 style={{ fontSize: 22, fontWeight: 800, color: '#0F172A', letterSpacing: '-0.02em' }}>Developer Intelligence</h1>
                    <div style={{ fontSize: 13, color: '#64748B', marginTop: 3 }}>AI-powered code optimization · Demo analysis</div>
                </div>
                <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                    <a href="/repositories" style={{
                        fontSize: 12, color: '#6366F1', textDecoration: 'none', fontWeight: 600,
                        padding: '7px 14px', border: '1px solid #C7D2FE', borderRadius: 8, background: '#EEF2FF',
                    }}>+ Add Repository</a>
                    <button
                        onClick={runAnalysis}
                        disabled={analyzing}
                        style={{
                            display: 'flex', alignItems: 'center', gap: 7,
                            padding: '8px 18px', borderRadius: 9, fontSize: 13, fontWeight: 600,
                            border: 'none', cursor: analyzing ? 'default' : 'pointer',
                            background: analyzing ? '#E2E8F0' : 'linear-gradient(135deg, #6366F1, #4F46E5)',
                            color: analyzing ? '#94A3B8' : '#fff', transition: 'all 0.2s',
                        }}>
                        {analyzing
                            ? <><Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} /> Analyzing…</>
                            : <><Activity size={13} /> Analyze Code</>}
                    </button>
                </div>
            </div>

            {/* Progress bar */}
            {(analyzing || done) && (
                <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #E2E8F0', padding: '16px 20px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                        <span style={{ fontSize: 13, fontWeight: 600, color: '#0F172A' }}>
                            {done ? '✅ Analysis Complete' : 'Running code analysis…'}
                        </span>
                        <span style={{ fontSize: 12, color: '#6366F1', fontWeight: 700 }}>{Math.min(100, Math.round(progress))}%</span>
                    </div>
                    <div style={{ height: 6, background: '#F1F5F9', borderRadius: 4, overflow: 'hidden' }}>
                        <div style={{
                            height: '100%', borderRadius: 4, transition: 'width 0.2s ease',
                            width: `${Math.min(100, progress)}%`,
                            background: done ? '#10B981' : 'linear-gradient(90deg, #6366F1, #8B5CF6)',
                        }} />
                    </div>
                    {done && (
                        <div style={{ fontSize: 12, color: '#64748B', marginTop: 8 }}>
                            Found <strong style={{ color: '#EF4444' }}>15 issues</strong> across 5 files ·
                            2 critical · 2 high · 1 medium
                        </div>
                    )}
                </div>
            )}

            {/* Stats */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 14 }}>
                <StatCard label="Total Files" value="47" sub="12 source files" />
                <StatCard label="Lines of Code" value="2,051" sub="Non-blank lines" />
                <StatCard label="Dependencies" value="23" sub="Across manifests" />
                <StatCard label="Issues Found" value={done ? '15' : '—'} color={done ? '#EF4444' : undefined} sub="After analysis" />
                <StatCard label="API Endpoints" value="9" sub="4 classes" />
            </div>

            {/* File list */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                <div className="card" style={{ padding: 20 }}>
                    <div style={{ fontSize: 14, fontWeight: 700, color: '#0F172A', marginBottom: 14 }}>Source Files</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                        {DEMO_FILES.map(f => (
                            <div key={f.name} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', borderRadius: 8, background: '#F8FAFC' }}>
                                <FileText size={13} color="#94A3B8" />
                                <span style={{ flex: 1, fontSize: 12, color: '#374151', fontFamily: 'monospace' }}>{f.name}</span>
                                <span style={{ fontSize: 10, color: '#94A3B8' }}>{f.loc} LOC</span>
                                {done && f.issues > 0 && (
                                    <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 5, background: '#FEF2F2', color: '#DC2626', fontWeight: 700 }}>
                                        {f.issues} issues
                                    </span>
                                )}
                                {done && (
                                    <div style={{ width: 36, height: 4, background: '#E2E8F0', borderRadius: 2 }}>
                                        <div style={{ height: '100%', width: `${f.risk * 100}%`, borderRadius: 2, background: f.risk > 0.7 ? '#EF4444' : f.risk > 0.4 ? '#F59E0B' : '#10B981' }} />
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                </div>

                <div className="card" style={{ padding: 20 }}>
                    <div style={{ fontSize: 14, fontWeight: 700, color: '#0F172A', marginBottom: 14 }}>Language Breakdown</div>
                    {[['Python', 34, '#3B82F6'], ['TypeScript', 8, '#8B5CF6'], ['YAML', 3, '#F59E0B'], ['Dockerfile', 2, '#10B981']].map(([lang, count, color]) => {
                        const total = 47;
                        const pct = Math.round((Number(count) / total) * 100);
                        return (
                            <div key={String(lang)} style={{ marginBottom: 12 }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                                    <span style={{ fontSize: 12, color: '#374151', fontWeight: 500 }}>{String(lang)}</span>
                                    <span style={{ fontSize: 11, color: '#94A3B8' }}>{String(count)} files · {pct}%</span>
                                </div>
                                <div style={{ height: 4, background: '#F1F5F9', borderRadius: 4 }}>
                                    <div style={{ height: '100%', width: `${pct}%`, background: String(color), borderRadius: 4 }} />
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* AI Suggestions — shown after analysis */}
            {done && (
                <div>
                    <div style={{ fontSize: 15, fontWeight: 700, color: '#0F172A', marginBottom: 12 }}>
                        🔍 Optimization Suggestions ({DEMO_SUGGESTIONS.length})
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                        {DEMO_SUGGESTIONS.map((s, i) => (
                            <div key={i} style={{
                                borderRadius: 10, border: '1px solid #E2E8F0',
                                background: '#FAFAFA', overflow: 'hidden',
                                borderLeft: `3px solid ${SEV_C[s.severity]}`,
                            }}>
                                <div
                                    style={{ padding: '12px 16px', display: 'flex', alignItems: 'flex-start', gap: 12, cursor: 'pointer' }}
                                    onClick={() => setExpanded(expanded === i ? null : i)}
                                >
                                    <span style={{ fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 5, background: SEV_BG[s.severity], color: SEV_C[s.severity], flexShrink: 0 }}>
                                        {s.severity}
                                    </span>
                                    <div style={{ flex: 1 }}>
                                        <div style={{ fontSize: 13, fontWeight: 600, color: '#0F172A', marginBottom: 2 }}>{s.title}</div>
                                        <div style={{ fontSize: 11, color: '#64748B', fontFamily: 'monospace' }}>{s.file}:{s.line}</div>
                                    </div>
                                    <span style={{
                                        fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 6,
                                        background: s.impact === 'Critical' ? '#FEF2F2' : s.impact === 'High' ? '#FFF7ED' : '#FFFBEB',
                                        color: s.impact === 'Critical' ? '#EF4444' : s.impact === 'High' ? '#F97316' : '#F59E0B',
                                    }}>{s.impact}</span>
                                    {expanded === i ? <ChevronDown size={14} color="#94A3B8" /> : <ChevronRight size={14} color="#94A3B8" />}
                                </div>
                                {expanded === i && (
                                    <div style={{ borderTop: '1px solid #E2E8F0', padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
                                        <div style={{ fontSize: 13, color: '#374151' }}>{s.description}</div>
                                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                                            <div>
                                                <div style={{ fontSize: 10, fontWeight: 700, color: '#DC2626', marginBottom: 4, textTransform: 'uppercase' }}>Before</div>
                                                <pre style={{ margin: 0, background: '#FEF2F2', border: '1px solid #FECACA', borderRadius: 6, padding: '8px 12px', fontSize: 11, color: '#7F1D1D', overflow: 'auto', fontFamily: 'monospace', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{s.before}</pre>
                                            </div>
                                            <div>
                                                <div style={{ fontSize: 10, fontWeight: 700, color: '#059669', marginBottom: 4, textTransform: 'uppercase' }}>After</div>
                                                <pre style={{ margin: 0, background: '#ECFDF5', border: '1px solid #A7F3D0', borderRadius: 6, padding: '8px 12px', fontSize: 11, color: '#064E3B', overflow: 'auto', fontFamily: 'monospace', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{s.after}</pre>
                                            </div>
                                        </div>
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {!done && !analyzing && (
                <div className="card" style={{ padding: 32, textAlign: 'center' }}>
                    <div style={{ width: 48, height: 48, borderRadius: 14, background: '#EEF2FF', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 14px' }}>
                        <Activity size={22} color="#6366F1" />
                    </div>
                    <div style={{ fontSize: 15, fontWeight: 600, color: '#0F172A', marginBottom: 6 }}>Ready to Analyze</div>
                    <div style={{ fontSize: 13, color: '#64748B', marginBottom: 18 }}>
                        Click <strong>Analyze Code</strong> above to scan for performance issues, security vulnerabilities, and optimization opportunities.
                    </div>
                    <button onClick={runAnalysis} style={{
                        padding: '10px 24px', borderRadius: 10, fontSize: 13, fontWeight: 600,
                        border: 'none', cursor: 'pointer',
                        background: 'linear-gradient(135deg, #6366F1, #4F46E5)', color: '#fff',
                    }}>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'center' }}>
                            <Zap size={14} /> Run Full Analysis
                        </span>
                    </button>
                </div>
            )}
        </div>
    );
}


export default function Developer() {
    const [searchParams] = useSearchParams();
    const repoParam = searchParams.get('repo');
    const { selectedProject } = useProject();

    // Use URL param first, fall back to selectedProject from global context
    const effectiveRepo = repoParam || selectedProject?.id || null;

    const [analysis, setAnalysis] = useState<any>(null);
    const [issues, setIssues] = useState<Issue[]>([]);
    const [loading, setLoading] = useState(false);
    const [loadingIssues, setLoadingIssues] = useState(false);
    const [activeTab, setActiveTab] = useState<'overview' | 'issues' | 'tree' | 'logs'>('overview');
    const [severityFilter, setSeverityFilter] = useState<string>('all');
    const [logs, setLogs] = useState<any[]>([]);
    const [logsEmpty, setLogsEmpty] = useState(false);
    const [expandedFiles, setExpandedFiles] = useState<Set<string>>(new Set());

    const load = useCallback(async () => {
        const repo = effectiveRepo;
        if (!repo) return;
        setLoading(true);
        try {
            const data = await api.getRepoAnalysis(repo);
            setAnalysis(data);
        } catch {
            setAnalysis(null);
        } finally {
            setLoading(false);
        }
    }, [effectiveRepo]);

    const loadIssues = useCallback(async () => {
        const repo = effectiveRepo;
        if (!repo) return;
        setLoadingIssues(true);
        try {
            // Try MongoDB errors endpoint first (has confidence score, resolve, RL feedback)
            // Falls back to legacy in-memory issues if MongoDB returns empty
            const mongoData: any = await api.getRepoErrors(repo);
            if (mongoData.errors && mongoData.errors.length > 0) {
                setIssues(mongoData.errors);
            } else {
                // Fallback to legacy issues endpoint (uses in-memory from repo_analyzer)
                const legacyData: any = await api.getRepoIssues(repo);
                setIssues(legacyData.issues || []);
            }
        } catch {
            setIssues([]);
        } finally {
            setLoadingIssues(false);
        }
    }, [effectiveRepo]);

    const loadLogs = useCallback(async () => {
        const repo = effectiveRepo;
        if (!repo) return;
        try {
            const data: any = await api.getRepoLogs(repo);
            if (data.empty_state) {
                setLogsEmpty(true);
                setLogs([]);
            } else {
                setLogsEmpty(false);
                setLogs(data.logs || []);
            }
        } catch {
            setLogsEmpty(true);
        }
    }, [effectiveRepo]);

    useEffect(() => { load(); }, [load]);

    useEffect(() => {
        if (activeTab === 'issues') loadIssues();
        else if (activeTab === 'logs') loadLogs();
    }, [activeTab, loadIssues, loadLogs]);

    // Reset state when project changes
    useEffect(() => {
        setAnalysis(null);
        setIssues([]);
        setLogs([]);
        setActiveTab('overview');
    }, [effectiveRepo]);

    const handleFeedback = (issueId: string, type: 'upvote' | 'downvote') => {
        setIssues(prev => prev.map(i => {
            const id = getIssueId(i);
            if (id !== issueId) return i;
            return {
                ...i,
                upvotes: (i.upvotes || 0) + (type === 'upvote' ? 1 : 0),
                downvotes: (i.downvotes || 0) + (type === 'downvote' ? 1 : 0),
                feedback: {
                    upvotes: ((i.feedback?.upvotes || 0) + (type === 'upvote' ? 1 : 0)),
                    downvotes: ((i.feedback?.downvotes || 0) + (type === 'downvote' ? 1 : 0)),
                },
            };
        }));
    };

    const handleResolve = (issueId: string) => {
        setIssues(prev => prev.filter(i => getIssueId(i) !== issueId));
    };

    const filteredIssues = severityFilter === 'all' ? issues : issues.filter(i => i.severity === severityFilter);

    // Sort: P1 → P2 → P3 → P4, then by confidence desc
    const sortedIssues = [...filteredIssues].sort((a, b) => {
        const sevOrd: Record<string, number> = { P1: 0, P2: 1, P3: 2, P4: 3 };
        const sevDiff = (sevOrd[a.severity] || 3) - (sevOrd[b.severity] || 3);
        if (sevDiff !== 0) return sevDiff;
        return (b.confidence_score || 0) - (a.confidence_score || 0);
    });

    if (!effectiveRepo) {
        return <DeveloperDemo />;
    }

    if (loading) {
        return (
            <div className="animate-fade" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                <div className="skeleton" style={{ height: 32, width: 300, borderRadius: 8 }} />
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14 }}>
                    {[1, 2, 3, 4].map(i => <div key={i} className="skeleton" style={{ height: 90, borderRadius: 10 }} />)}
                </div>
                <div className="skeleton" style={{ height: 200, borderRadius: 10 }} />
            </div>
        );
    }

    const status = analysis?.status;
    const isAnalyzing = status === 'analyzing';

    if (!analysis || isAnalyzing) {
        return (
            <div className="animate-fade" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                <h1 style={{ fontSize: 22, fontWeight: 800, color: '#0F172A' }}>{repoParam}</h1>
                <div className="card" style={{ padding: 48, textAlign: 'center' }}>
                    <Loader2 size={28} color="#6366F1" style={{ animation: 'spin 1s linear infinite', margin: '0 auto 16px' }} />
                    <div style={{ fontSize: 15, fontWeight: 600, color: '#0F172A', marginBottom: 6 }}>Analysis in progress…</div>
                    <div style={{ fontSize: 13, color: '#64748B' }}>
                        Fetching repository data and running AI analysis.
                        This takes 30–120 seconds depending on repo size.
                    </div>
                    <button className="btn btn-secondary" style={{ margin: '16px auto 0', display: 'flex' }} onClick={load}>
                        <RefreshCw size={13} /> Check status
                    </button>
                </div>
            </div>
        );
    }

    const tabs = ['overview', 'issues', 'tree', 'logs'] as const;

    return (
        <div className="animate-fade" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <h1 style={{ fontSize: 20, fontWeight: 800, color: '#0F172A' }}>{analysis.name}</h1>
                        <span style={{ fontSize: 12, padding: '2px 8px', borderRadius: 9999, background: '#EEF2FF', color: '#6366F1', fontWeight: 600 }}>
                            {analysis.language || 'Unknown'}
                        </span>
                        {analysis.stars > 0 && (
                            <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: '#94A3B8' }}>
                                <Star size={12} fill="#F59E0B" color="#F59E0B" /> {analysis.stars}
                            </span>
                        )}
                    </div>
                    <div style={{ fontSize: 13, color: '#64748B', marginTop: 3 }}>
                        {analysis.description || analysis.repo_id} · Analyzed {analysis.analyzed_at ? new Date(analysis.analyzed_at).toLocaleString() : 'recently'}
                    </div>
                </div>
                <div style={{ display: 'flex', gap: 10 }}>
                    <a href={analysis.repo_url} target="_blank" rel="noreferrer"
                        style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#6366F1', textDecoration: 'none', fontWeight: 600 }}>
                        <ExternalLink size={13} /> GitHub
                    </a>
                    <button className="btn btn-secondary" onClick={() => { setLoading(true); load(); }}>
                        <RefreshCw size={13} /> Re-scan
                    </button>
                </div>
            </div>

            {/* Stats row */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 14 }}>
                <StatCard label="Total Files" value={analysis.total_files?.toLocaleString() ?? '—'} sub={`${analysis.source_files || 0} source files`} />
                <StatCard label="Lines of Code" value={analysis.total_loc?.toLocaleString() ?? '—'} sub="Non-blank lines" />
                <StatCard label="Dependencies" value={analysis.total_dependencies ?? '—'} sub="Across all manifests" />
                <StatCard label="Issues Found" value={analysis.issues_found ?? 0}
                    color={(analysis.issues_found || 0) > 0 ? '#EF4444' : '#059669'}
                    sub={`${analysis.code_structure?.total_functions || 0} functions`} />
                <StatCard label="API Endpoints" value={analysis.code_structure?.api_endpoints?.length || 0}
                    sub={`${analysis.code_structure?.total_classes || 0} classes`} />
            </div>

            {/* Tabs */}
            <div style={{ display: 'flex', borderBottom: '2px solid #F1F5F9', gap: 0 }}>
                {tabs.map(tab => (
                    <button key={tab} onClick={() => setActiveTab(tab)}
                        style={{
                            padding: '10px 18px', border: 'none', background: 'none', cursor: 'pointer',
                            fontSize: 13, fontWeight: activeTab === tab ? 700 : 600,
                            color: activeTab === tab ? '#6366F1' : '#64748B',
                            borderBottom: `2px solid ${activeTab === tab ? '#6366F1' : 'transparent'}`,
                            marginBottom: -2, transition: 'all 0.15s', textTransform: 'capitalize',
                        }}>
                        {tab === 'issues' ? `Issues (${analysis.issues_found || 0})` : tab.charAt(0).toUpperCase() + tab.slice(1)}
                    </button>
                ))}
            </div>

            {/* Tab content */}
            {activeTab === 'overview' && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                    {/* Gemini analysis card */}
                    <div className="card" style={{ padding: 20, gridColumn: '1 / -1' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                            <Activity size={16} color="#6366F1" />
                            <div style={{ fontSize: 14, fontWeight: 700, color: '#0F172A' }}>Gemini AI Analysis</div>
                        </div>
                        <div style={{ fontSize: 13, color: '#374151', lineHeight: 1.7 }}>
                            {analysis.gemini_analysis || 'Analysis not available.'}
                        </div>
                    </div>

                    {/* Language breakdown */}
                    <div className="card" style={{ padding: 20 }}>
                        <div style={{ fontSize: 14, fontWeight: 700, color: '#0F172A', marginBottom: 14 }}>Language Breakdown</div>
                        {Object.entries(analysis.language_breakdown || {})
                            .sort(([, a]: any, [, b]: any) => b - a)
                            .slice(0, 10)
                            .map(([ext, count]: any) => {
                                const total = Object.values(analysis.language_breakdown || {}).reduce((a: any, b: any) => a + b, 0) as number;
                                const pct = total > 0 ? Math.round((count / total) * 100) : 0;
                                return (
                                    <div key={ext} style={{ marginBottom: 10 }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                                            <span style={{ fontSize: 12, color: '#374151', fontWeight: 500 }}>{ext}</span>
                                            <span style={{ fontSize: 11, color: '#94A3B8' }}>{count} files · {pct}%</span>
                                        </div>
                                        <div style={{ height: 4, background: '#F1F5F9', borderRadius: 4 }}>
                                            <div style={{ height: '100%', width: `${pct}%`, background: '#6366F1', borderRadius: 4 }} />
                                        </div>
                                    </div>
                                );
                            })}
                    </div>

                    {/* Top complex files */}
                    <div className="card" style={{ padding: 20 }}>
                        <div style={{ fontSize: 14, fontWeight: 700, color: '#0F172A', marginBottom: 14 }}>Most Complex Files</div>
                        {Object.entries(analysis.code_structure?.complexity_scores || {})
                            .slice(0, 8)
                            .map(([path, score]: any) => (
                                <div key={path} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                                    <span style={{
                                        fontSize: 11, color: '#374151', fontFamily: 'monospace',
                                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1
                                    }}>
                                        {path.split('/').pop()}
                                    </span>
                                    <span style={{
                                        fontSize: 11, fontWeight: 700, color: score > 50 ? '#EF4444' : score > 20 ? '#F59E0B' : '#10B981',
                                        fontFamily: 'monospace', marginLeft: 8
                                    }}>
                                        {score}
                                    </span>
                                </div>
                            ))}
                        {Object.keys(analysis.code_structure?.complexity_scores || {}).length === 0 && (
                            <div style={{ fontSize: 12, color: '#94A3B8' }}>No complexity data yet</div>
                        )}
                    </div>

                    {/* Dependency details */}
                    {(analysis.dependency_details || []).length > 0 && (
                        <div className="card" style={{ padding: 20, gridColumn: '1 / -1' }}>
                            <div style={{ fontSize: 14, fontWeight: 700, color: '#0F172A', marginBottom: 14 }}>
                                <Package size={14} color="#6366F1" style={{ display: 'inline', marginRight: 6 }} />
                                Dependencies ({analysis.total_dependencies} total)
                            </div>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 10 }}>
                                {(analysis.dependency_details || []).map((dep: any) => (
                                    <div key={dep.file} style={{ background: '#F8FAFC', borderRadius: 8, padding: '10px 14px' }}>
                                        <div style={{ fontSize: 11, fontWeight: 600, color: '#374151', marginBottom: 4 }}>
                                            {dep.file.split('/').pop()} ({dep.count})
                                        </div>
                                        <div style={{ fontSize: 11, color: '#94A3B8', lineHeight: 1.5 }}>
                                            {(dep.packages || []).join(', ') || 'None listed'}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {activeTab === 'issues' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                    {/* Severity filter */}
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        <span style={{ fontSize: 12, color: '#64748B', fontWeight: 600 }}>Filter:</span>
                        {['all', 'P1', 'P2', 'P3', 'P4'].map(sev => (
                            <button key={sev} onClick={() => setSeverityFilter(sev)}
                                style={{
                                    padding: '4px 12px', borderRadius: 7, fontSize: 12, fontWeight: 600,
                                    border: `1px solid ${severityFilter === sev ? '#6366F1' : '#E2E8F0'}`,
                                    background: severityFilter === sev ? '#EEF2FF' : '#fff',
                                    color: severityFilter === sev ? '#6366F1' : '#64748B',
                                    cursor: 'pointer',
                                }}>
                                {sev === 'all' ? `All (${issues.length})` : `${sev} (${issues.filter(i => i.severity === sev).length})`}
                            </button>
                        ))}
                    </div>

                    {loadingIssues && (
                        <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
                            <Loader2 size={24} color="#6366F1" style={{ animation: 'spin 1s linear infinite' }} />
                        </div>
                    )}

                    {!loadingIssues && filteredIssues.length === 0 && (
                        <div className="card" style={{ padding: 48, textAlign: 'center' }}>
                            <CheckCircle size={28} color="#10B981" style={{ margin: '0 auto 12px' }} />
                            <div style={{ fontSize: 15, fontWeight: 600, color: '#0F172A', marginBottom: 6 }}>
                                {severityFilter === 'all' ? 'Repository looks healthy — zero issues found' : `No ${severityFilter} issues`}
                            </div>
                            <div style={{ fontSize: 13, color: '#64748B' }}>
                                {severityFilter === 'all'
                                    ? 'Phi-3 and static analysis found no issues in this repository. Nice work!'
                                    : 'Try selecting a different severity filter.'}
                            </div>
                        </div>
                    )}

                    {sortedIssues.map(issue => (
                        <IssueCard key={getIssueId(issue)} issue={issue} repoId={effectiveRepo!}
                            onFeedback={handleFeedback} onResolve={handleResolve} />
                    ))}
                </div>
            )}

            {activeTab === 'tree' && (
                <div className="card" style={{ padding: 20 }}>
                    <div style={{ fontSize: 14, fontWeight: 700, color: '#0F172A', marginBottom: 16 }}>
                        File Tree · {(analysis.file_tree || []).length} entries shown
                    </div>
                    <div style={{ fontFamily: 'monospace', fontSize: 12 }}>
                        {(analysis.file_tree || []).map((f: FileTreeItem, i: number) => {
                            const depth = f.path.split('/').length - 1;
                            const issueColor = (f.issues || 0) > 0
                                ? SEV_COLOR['P2'] : '#10B981';
                            return (
                                <div key={i} style={{
                                    display: 'flex', alignItems: 'center', gap: 8,
                                    padding: '3px 0', paddingLeft: depth * 16,
                                    borderBottom: i < (analysis.file_tree || []).length - 1 ? '1px solid #F8FAFC' : 'none',
                                }}>
                                    {f.type === 'dir'
                                        ? <GitBranch size={12} color="#94A3B8" />
                                        : <FileText size={12} color="#64748B" />}
                                    <span style={{ flex: 1, color: '#374151', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                        {f.name}
                                    </span>
                                    {f.loc && <span style={{ color: '#94A3B8', fontSize: 10 }}>{f.loc} LOC</span>}
                                    {(f.issues || 0) > 0 && (
                                        <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 4, background: '#FEF2F2', color: issueColor, fontWeight: 700 }}>
                                            {f.issues} {(f.issues || 0) === 1 ? 'issue' : 'issues'}
                                        </span>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            {activeTab === 'logs' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                    {logsEmpty ? (
                        <div className="card" style={{ padding: 32, textAlign: 'center' }}>
                            <Info size={24} color="#94A3B8" style={{ margin: '0 auto 12px' }} />
                            <div style={{ fontSize: 14, fontWeight: 600, color: '#0F172A', marginBottom: 6 }}>No runtime logs available</div>
                            <div style={{ fontSize: 13, color: '#64748B', maxWidth: 400, margin: 'auto' }}>
                                Install the NeuralOps SDK in your application to stream real-time logs here.
                                GitHub Actions run history is shown if available.
                            </div>
                        </div>
                    ) : (
                        <div className="card" style={{ padding: 16 }}>
                            {logs.map((log: any, i: number) => (
                                <div key={i} style={{
                                    display: 'flex', gap: 12, padding: '8px 0', alignItems: 'flex-start',
                                    borderBottom: i < logs.length - 1 ? '1px solid #F8FAFC' : 'none',
                                }}>
                                    <span style={{
                                        fontSize: 10, fontWeight: 700, padding: '2px 6px', borderRadius: 4, whiteSpace: 'nowrap',
                                        background: log.level === 'ERROR' ? '#FEF2F2' : '#F0FDF4',
                                        color: log.level === 'ERROR' ? '#DC2626' : '#059669',
                                    }}>{log.level}</span>
                                    <span style={{ fontSize: 12, color: '#374151', flex: 1 }}>{log.message}</span>
                                    {log.timestamp && (
                                        <span style={{ fontSize: 10, color: '#94A3B8', whiteSpace: 'nowrap' }}>
                                            {new Date(log.timestamp).toLocaleString()}
                                        </span>
                                    )}
                                    {log.url && (
                                        <a href={log.url} target="_blank" rel="noreferrer" style={{ color: '#6366F1' }}>
                                            <ExternalLink size={11} />
                                        </a>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
