// frontend/src/pages/Predictions.tsx
import { useState } from 'react';
import {
    TrendingUp, TrendingDown, Activity, BellOff, Search, RefreshCw,
    AlertTriangle, X, Zap, CheckCircle, Info, Code2
} from 'lucide-react';
import { LineChart, Line, ResponsiveContainer, Tooltip } from 'recharts';

interface Prediction {
    id: string;
    service: string;
    metric: string;
    severity: 'P1' | 'P2' | 'P3' | 'P4';
    confidence: number;
    predicted_at_hours: number;
    description: string;
    trend: 'up' | 'down';
    current_value: number;
    predicted_value: number;
    unit: string;
    sparkline: { t: number; v: number }[];
    snoozed?: boolean;
    applied?: boolean; // Fix has been applied
    // Investigation data
    root_cause?: string;
    code_changes?: CodeChange[];
    impact_level?: 'Critical' | 'High' | 'Medium' | 'Low';
}

interface CodeChange {
    file: string;
    issue: string;
    before: string;
    after: string;
    impact: 'Critical' | 'High' | 'Medium' | 'Low';
}

const SEVERITY_COLOR: Record<string, string> = {
    P1: '#EF4444', P2: '#F97316', P3: '#F59E0B', P4: '#6366F1',
};

const IMPACT_COLOR: Record<string, string> = {
    Critical: '#EF4444', High: '#F97316', Medium: '#F59E0B', Low: '#10B981',
};
const IMPACT_BG: Record<string, string> = {
    Critical: '#FEF2F2', High: '#FFF7ED', Medium: '#FFFBEB', Low: '#F0FDF4',
};

function mkSparkline(base: number, end: number, noise = 3) {
    return Array.from({ length: 20 }, (_, i) => ({
        t: i,
        v: +(base + ((end - base) * i / 19) + (Math.random() - 0.5) * noise).toFixed(1),
    }));
}

const now = new Date();
const hoursAgo = (h: number) => new Date(now.getTime() - h * 3_600_000).toISOString();

const MOCK_PREDICTIONS: Prediction[] = [
    {
        id: 'p1', service: 'api-gateway', metric: 'CPU Usage', severity: 'P2',
        confidence: 0.91, predicted_at_hours: 1.5, trend: 'up',
        current_value: 68, predicted_value: 95, unit: '%',
        sparkline: mkSparkline(68, 95, 4),
        description: 'CPU is trending toward saturation. Predicted to hit 95% in ~90 minutes based on current request rate growth.',
        root_cause: 'Unbounded connection pool in the API gateway is creating excessive threads per request, causing CPU to spike under load.',
        impact_level: 'High',
        code_changes: [
            {
                file: 'src/server/connection_pool.py',
                issue: 'Connection pool has no max size limit — threads accumulate under load',
                before: `pool = ConnectionPool(\n    host=DB_HOST,\n    port=DB_PORT\n)`,
                after: `pool = ConnectionPool(\n    host=DB_HOST,\n    port=DB_PORT,\n    max_connections=50,\n    timeout=30\n)`,
                impact: 'High',
            },
            {
                file: 'src/middleware/rate_limiter.py',
                issue: 'Rate limiter not applied to heavy /analyze endpoints — allows burst traffic',
                before: `@app.route('/analyze')\ndef analyze():\n    return run_analysis()`,
                after: `@app.route('/analyze')\n@rate_limit(max_calls=100, period=60)\ndef analyze():\n    return run_analysis()`,
                impact: 'Medium',
            },
        ],
    },
    {
        id: 'p2', service: 'ml-inference', metric: 'Memory Usage', severity: 'P1',
        confidence: 0.87, predicted_at_hours: 0.5, trend: 'up',
        current_value: 5.8, predicted_value: 8.0, unit: 'GB',
        sparkline: mkSparkline(5.8, 8.0, 0.2),
        description: 'Memory leak detected. RSS growing 45MB/hour. OOM kill predicted in ~30 minutes.',
        root_cause: 'Model tensors are not being released after inference. Each request creates a new model copy in memory without cleanup.',
        impact_level: 'Critical',
        code_changes: [
            {
                file: 'src/inference/model_runner.py',
                issue: 'Model loaded fresh per request — never garbage collected',
                before: `def predict(data):\n    model = load_model('model.pkl')\n    return model.predict(data)`,
                after: `# Load once at startup\n_MODEL = load_model('model.pkl')\n\ndef predict(data):\n    return _MODEL.predict(data)`,
                impact: 'Critical',
            },
            {
                file: 'src/inference/tensor_cache.py',
                issue: 'Tensors stored in a dict that grows without bound',
                before: `cache = {}\n\ndef store(key, tensor):\n    cache[key] = tensor`,
                after: `from functools import lru_cache\n\n@lru_cache(maxsize=128)\ndef store(key, tensor):\n    return tensor`,
                impact: 'High',
            },
        ],
    },
    {
        id: 'p3', service: 'data-ingestion', metric: 'Error Rate', severity: 'P3',
        confidence: 0.76, predicted_at_hours: 4, trend: 'up',
        current_value: 0.5, predicted_value: 4.2, unit: '%',
        sparkline: mkSparkline(0.5, 4.2, 0.3),
        description: 'Upstream Kafka lag increasing. Error rate expected to spike when consumer falls behind by >10k messages.',
        root_cause: 'Kafka consumer group has a single partition consumer — no parallelism under high throughput.',
        impact_level: 'Medium',
        code_changes: [
            {
                file: 'src/ingestion/kafka_consumer.py',
                issue: 'Single partition consumer — bottleneck at high volume',
                before: `consumer = KafkaConsumer('events',\n    group_id='ingestion-group'\n)`,
                after: `consumer = KafkaConsumer('events',\n    group_id='ingestion-group',\n    max_poll_records=500,\n    fetch_max_bytes=52428800\n)`,
                impact: 'Medium',
            },
        ],
    },
    {
        id: 'p4', service: 'postgres-primary', metric: 'Disk Usage', severity: 'P2',
        confidence: 0.94, predicted_at_hours: 48, trend: 'up',
        current_value: 72, predicted_value: 100, unit: '%',
        sparkline: mkSparkline(72, 95, 1),
        description: 'Write-ahead log accumulation detected. Disk will fill in ~48 hours without log rotation.',
        root_cause: 'WAL archiving is enabled but archive_cleanup_command is not configured, causing WAL segments to accumulate.',
        impact_level: 'High',
        code_changes: [
            {
                file: 'postgresql.conf',
                issue: 'archive_cleanup_command not set — WAL logs accumulate indefinitely',
                before: `archive_mode = on\narchive_command = 'cp %p /archive/%f'`,
                after: `archive_mode = on\narchive_command = 'cp %p /archive/%f'\narchive_cleanup_command = 'pg_archivecleanup /archive %r'\nwal_keep_size = 1024`,
                impact: 'High',
            },
        ],
    },
    {
        id: 'p5', service: 'redis-cache', metric: 'Hit Rate', severity: 'P4',
        confidence: 0.68, predicted_at_hours: 6, trend: 'down',
        current_value: 93, predicted_value: 78, unit: '%',
        sparkline: mkSparkline(93, 78, 2),
        description: 'Cache eviction rate increasing. Hit rate predicted to drop, increasing database load.',
        root_cause: 'TTL values are too short for frequently accessed keys, causing premature eviction.',
        impact_level: 'Low',
        code_changes: [
            {
                file: 'src/cache/redis_client.py',
                issue: 'TTL too low for hot user session keys',
                before: `redis.set(key, value, ex=300)  # 5 min TTL`,
                after: `redis.set(key, value, ex=3600)  # 1 hour TTL for sessions`,
                impact: 'Low',
            },
        ],
    },
];

function InvestigateModal({
    pred, onClose, onApply,
}: {
    pred: Prediction;
    onClose: () => void;
    onApply: (id: string) => void;
}) {
    const [investigatingStep, setInvestigatingStep] = useState(0);
    const [applying, setApplying] = useState(false);
    const [applied, setApplied] = useState(pred.applied ?? false);
    const steps = ['Analyzing metrics…', 'Scanning codebase…', 'Generating recommendations…', 'Done'];

    // Auto-progress through steps
    useState(() => {
        let step = 0;
        const interval = setInterval(() => {
            step++;
            setInvestigatingStep(step);
            if (step >= steps.length - 1) clearInterval(interval);
        }, 700);
        return () => clearInterval(interval);
    });

    const done = investigatingStep >= steps.length - 1;

    const handleApply = async () => {
        setApplying(true);
        await new Promise(r => setTimeout(r, 2200));
        setApplying(false);
        setApplied(true);
        onApply(pred.id);
    };

    return (
        <div style={{
            position: 'fixed', inset: 0, zIndex: 1000,
            background: 'rgba(15,23,42,0.6)', backdropFilter: 'blur(4px)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: 24,
        }} onClick={onClose}>
            <div style={{
                background: '#fff', borderRadius: 20, width: '100%', maxWidth: 680,
                maxHeight: '88vh', overflow: 'hidden', display: 'flex', flexDirection: 'column',
                boxShadow: '0 24px 64px rgba(0,0,0,0.18)',
            }} onClick={e => e.stopPropagation()}>

                {/* Modal header */}
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
                            {pred.service} · {pred.metric}
                        </div>
                    </div>
                    <span style={{
                        fontSize: 11, fontWeight: 700, padding: '4px 10px',
                        borderRadius: 8, background: `${SEVERITY_COLOR[pred.severity]}15`,
                        color: SEVERITY_COLOR[pred.severity],
                    }}>{pred.severity}</span>
                    <button onClick={onClose} style={{
                        background: '#F1F5F9', border: 'none', borderRadius: 8,
                        padding: 7, cursor: 'pointer', display: 'flex',
                    }}>
                        <X size={15} color="#64748B" />
                    </button>
                </div>

                {/* Progress steps */}
                {!done && (
                    <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: 14 }}>
                        {steps.slice(0, -1).map((step, i) => (
                            <div key={step} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                                <div style={{
                                    width: 28, height: 28, borderRadius: '50%', flexShrink: 0,
                                    background: investigatingStep > i ? '#10B981' : investigatingStep === i ? '#6366F1' : '#F1F5F9',
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    transition: 'all 0.3s',
                                }}>
                                    {investigatingStep > i
                                        ? <CheckCircle size={14} color="#fff" />
                                        : investigatingStep === i
                                            ? <div style={{ width: 10, height: 10, borderRadius: '50%', border: '2px solid #fff', borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite' }} />
                                            : <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#CBD5E1' }} />}
                                </div>
                                <span style={{
                                    fontSize: 13, color: investigatingStep >= i ? '#0F172A' : '#94A3B8',
                                    fontWeight: investigatingStep === i ? 600 : 400,
                                }}>{step}</span>
                            </div>
                        ))}
                    </div>
                )}

                {/* Full report once done */}
                {done && (
                    <div style={{ overflowY: 'auto', padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 20 }}>

                        {/* Root cause */}
                        <div style={{ background: '#FFF7ED', border: '1px solid #FED7AA', borderRadius: 12, padding: '16px 18px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                                <Info size={15} color="#EA580C" />
                                <span style={{ fontSize: 12, fontWeight: 700, color: '#EA580C', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Root Cause</span>
                            </div>
                            <div style={{ fontSize: 13, color: '#7C2D12', lineHeight: 1.7 }}>
                                {pred.root_cause}
                            </div>
                        </div>

                        {/* Severity assessment */}
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
                            {[
                                { label: 'Impact Level', value: pred.impact_level ?? 'Medium', colored: true },
                                { label: 'Confidence', value: `${Math.round(pred.confidence * 100)}%`, colored: false },
                                { label: 'Time to Impact', value: pred.predicted_at_hours < 1 ? `${Math.round(pred.predicted_at_hours * 60)}m` : `${pred.predicted_at_hours}h`, colored: false },
                            ].map(stat => (
                                <div key={stat.label} style={{
                                    background: stat.colored ? IMPACT_BG[stat.value] : '#F8FAFC',
                                    borderRadius: 10, padding: '12px 16px',
                                    border: stat.colored ? `1px solid ${IMPACT_COLOR[stat.value]}30` : '1px solid #E2E8F0',
                                }}>
                                    <div style={{ fontSize: 10, fontWeight: 600, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>{stat.label}</div>
                                    <div style={{ fontSize: 18, fontWeight: 800, color: stat.colored ? IMPACT_COLOR[stat.value] : '#0F172A' }}>{stat.value}</div>
                                </div>
                            ))}
                        </div>

                        {/* Code changes */}
                        <div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                                <Code2 size={15} color="#6366F1" />
                                <span style={{ fontSize: 14, fontWeight: 700, color: '#0F172A' }}>
                                    Recommended Code Changes ({pred.code_changes?.length ?? 0})
                                </span>
                            </div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                                {(pred.code_changes ?? []).map((change, i) => (
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
                                                fontSize: 10, fontWeight: 700, padding: '2px 8px',
                                                borderRadius: 6, background: IMPACT_BG[change.impact],
                                                color: IMPACT_COLOR[change.impact],
                                            }}>{change.impact}</span>
                                        </div>
                                        <div style={{ padding: '10px 14px', fontSize: 12, color: '#374151', borderBottom: '1px solid #F1F5F9' }}>
                                            ⚠️ {change.issue}
                                        </div>
                                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0 }}>
                                            <div style={{ padding: '10px 14px', borderRight: '1px solid #F1F5F9' }}>
                                                <div style={{ fontSize: 10, fontWeight: 700, color: '#DC2626', marginBottom: 6 }}>BEFORE</div>
                                                <pre style={{
                                                    margin: 0, fontSize: 11, background: '#FEF2F2',
                                                    borderRadius: 6, padding: '8px 10px', color: '#7F1D1D',
                                                    overflow: 'auto', fontFamily: 'monospace', whiteSpace: 'pre-wrap',
                                                }}>{change.before}</pre>
                                            </div>
                                            <div style={{ padding: '10px 14px' }}>
                                                <div style={{ fontSize: 10, fontWeight: 700, color: '#059669', marginBottom: 6 }}>AFTER</div>
                                                <pre style={{
                                                    margin: 0, fontSize: 11, background: '#ECFDF5',
                                                    borderRadius: 6, padding: '8px 10px', color: '#064E3B',
                                                    overflow: 'auto', fontFamily: 'monospace', whiteSpace: 'pre-wrap',
                                                }}>{change.after}</pre>
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                )}

                {/* Footer */}
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
                        {applied ? (
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 18px', borderRadius: 9, background: '#ECFDF5', border: '1px solid #A7F3D0', color: '#059669', fontWeight: 700, fontSize: 13 }}>
                                <CheckCircle size={14} /> Fixes Applied Successfully
                            </div>
                        ) : (
                            <button
                                onClick={handleApply}
                                disabled={applying}
                                style={{
                                    display: 'flex', alignItems: 'center', gap: 7,
                                    padding: '8px 18px', borderRadius: 9, fontSize: 13,
                                    border: 'none',
                                    background: applying ? '#E2E8F0' : 'linear-gradient(135deg, #6366F1, #4F46E5)',
                                    cursor: applying ? 'default' : 'pointer',
                                    color: applying ? '#94A3B8' : '#fff', fontWeight: 600,
                                }}>
                                {applying
                                    ? <><div style={{ width: 13, height: 13, border: '2px solid #94A3B8', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} /> Applying Fixes…</>
                                    : <><Zap size={13} /> Apply Fixes</>}
                            </button>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}

export default function Predictions() {
    const [predictions, setPredictions] = useState<Prediction[]>(MOCK_PREDICTIONS);
    const [searchText, setSearchText] = useState('');
    const [filterSev, setFilterSev] = useState('');
    const [loading, setLoading] = useState(false);
    const [investigating, setInvestigating] = useState<Prediction | null>(null);

    const filtered = predictions.filter(p => !p.snoozed
        && (!filterSev || p.severity === filterSev)
        && (!searchText || p.service.includes(searchText) || p.metric.toLowerCase().includes(searchText.toLowerCase()))
    );

    const refresh = async () => {
        setLoading(true);
        await new Promise(res => setTimeout(res, 800));
        setLoading(false);
    };

    const snooze = (id: string) => setPredictions(prev => prev.map(p => p.id === id ? { ...p, snoozed: true } : p));

    return (
        <div className="animate-fade" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {investigating && <InvestigateModal
                pred={investigating}
                onClose={() => setInvestigating(null)}
                onApply={(id) => {
                    setPredictions(prev => prev.map(p => {
                        if (p.id !== id) return p;
                        const sevMap: Record<string, Prediction['severity']> = { P1: 'P2', P2: 'P3', P3: 'P4', P4: 'P4' };
                        const newPredicted = p.current_value + (p.predicted_value - p.current_value) * 0.25;
                        return {
                            ...p,
                            applied: true,
                            severity: sevMap[p.severity],
                            predicted_value: +newPredicted.toFixed(1),
                            confidence: Math.max(0.2, p.confidence - 0.35),
                            sparkline: mkSparkline(p.current_value, newPredicted, 1.5),
                        };
                    }));
                    setInvestigating(null);
                }}
            />}

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                    <h1 style={{ fontSize: 22, fontWeight: 800, color: '#0F172A', letterSpacing: '-0.02em' }}>Predictions</h1>
                    <div style={{ fontSize: 13, color: '#64748B', marginTop: 3 }}>
                        ML-powered failure forecasts · {filtered.length} active predictions
                    </div>
                </div>
                <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                    <div style={{ position: 'relative' }}>
                        <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: '#94A3B8' }} />
                        <input className="form-input" value={searchText} onChange={e => setSearchText(e.target.value)} placeholder="Search service…" style={{ paddingLeft: 32, width: 200 }} />
                    </div>
                    <select className="form-select" value={filterSev} onChange={e => setFilterSev(e.target.value)}>
                        {['', 'P1', 'P2', 'P3', 'P4'].map(s => <option key={s} value={s}>{s || 'All Severities'}</option>)}
                    </select>
                    <button className="btn btn-secondary" onClick={refresh} disabled={loading}>
                        <RefreshCw size={13} style={loading ? { animation: 'spin 1s linear infinite' } : {}} />
                    </button>
                </div>
            </div>

            {/* Overview row */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
                {[
                    { label: 'Critical (P1)', count: predictions.filter(p => p.severity === 'P1' && !p.snoozed).length, color: '#EF4444' },
                    { label: 'High (P2)', count: predictions.filter(p => p.severity === 'P2' && !p.snoozed).length, color: '#F97316' },
                    { label: 'Medium (P3)', count: predictions.filter(p => p.severity === 'P3' && !p.snoozed).length, color: '#F59E0B' },
                    { label: 'Low (P4)', count: predictions.filter(p => p.severity === 'P4' && !p.snoozed).length, color: '#6366F1' },
                ].map(s => (
                    <div key={s.label} className="card" style={{ padding: '16px 20px' }}>
                        <div style={{ fontSize: 11, fontWeight: 600, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{s.label}</div>
                        <div style={{ fontSize: 28, fontWeight: 800, color: s.count > 0 ? s.color : '#0F172A', marginTop: 6, letterSpacing: '-0.02em' }}>{s.count}</div>
                    </div>
                ))}
            </div>

            {/* Prediction cards */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {filtered.map(pred => (
                    <div key={pred.id} className="card" style={{ padding: '20px 24px', borderLeft: `3px solid ${SEVERITY_COLOR[pred.severity]}` }}>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 16, alignItems: 'start' }}>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                                {/* Top row */}
                                <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                                    <span className={`badge badge-${pred.severity.toLowerCase()}`}>{pred.severity}</span>
                                    {pred.applied && (
                                        <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, padding: '2px 9px', borderRadius: 9999, background: '#ECFDF5', color: '#059669', fontWeight: 700, border: '1px solid #A7F3D0' }}>
                                            <CheckCircle size={10} /> Fixes Applied
                                        </span>
                                    )}
                                    <span style={{ fontWeight: 700, fontSize: 14, color: '#0F172A' }}>{pred.service}</span>
                                    <span style={{ fontSize: 13, color: '#64748B' }}>·</span>
                                    <span style={{ fontSize: 13, color: '#64748B' }}>{pred.metric}</span>
                                    <span style={{ fontSize: 11, padding: '2px 10px', borderRadius: 9999, background: '#EEF2FF', color: '#6366F1', fontWeight: 600 }}>
                                        {pred.confidence * 100 | 0}% confidence
                                    </span>
                                    <span style={{ fontSize: 11, color: pred.predicted_at_hours < 1 ? '#EF4444' : pred.predicted_at_hours < 4 ? '#F59E0B' : '#64748B' }}>
                                        ⏱ ~{pred.predicted_at_hours < 1 ? `${Math.round(pred.predicted_at_hours * 60)}m` : `${pred.predicted_at_hours.toFixed(1)}h`} away
                                    </span>
                                    {pred.impact_level && (
                                        <span style={{
                                            fontSize: 11, padding: '2px 10px', borderRadius: 9999,
                                            background: IMPACT_BG[pred.impact_level],
                                            color: IMPACT_COLOR[pred.impact_level], fontWeight: 700,
                                        }}>
                                            {pred.impact_level}
                                        </span>
                                    )}
                                </div>

                                <div style={{ fontSize: 13, color: '#334155', lineHeight: 1.7 }}>{pred.description}</div>

                                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                                    <div style={{ fontSize: 12, color: '#64748B' }}>
                                        Current: <strong style={{ color: '#0F172A' }}>{pred.current_value}{pred.unit}</strong>
                                    </div>
                                    {pred.trend === 'up' ? <TrendingUp size={14} color="#EF4444" /> : <TrendingDown size={14} color="#F59E0B" />}
                                    <div style={{ fontSize: 12, color: '#64748B' }}>
                                        Predicted: <strong style={{ color: pred.trend === 'up' ? '#EF4444' : '#F59E0B' }}>{pred.predicted_value}{pred.unit}</strong>
                                    </div>
                                </div>

                                {/* Actions */}
                                <div style={{ display: 'flex', gap: 8 }}>
                                    <button
                                        className="btn btn-primary"
                                        style={{ fontSize: 12, padding: '6px 16px', display: 'flex', alignItems: 'center', gap: 6 }}
                                        onClick={() => setInvestigating(pred)}
                                    >
                                        <AlertTriangle size={12} /> Investigate
                                    </button>
                                    <button
                                        className="btn btn-secondary"
                                        style={{ fontSize: 12, padding: '6px 14px' }}
                                        onClick={() => snooze(pred.id)}
                                    >
                                        <BellOff size={12} /> Snooze
                                    </button>
                                </div>
                            </div>

                            {/* Sparkline */}
                            <div style={{ width: 140, height: 60 }}>
                                <ResponsiveContainer width="100%" height="100%">
                                    <LineChart data={pred.sparkline}>
                                        <Line type="monotone" dataKey="v" stroke={SEVERITY_COLOR[pred.severity]} strokeWidth={2} dot={false} />
                                        <Tooltip content={() => null} />
                                    </LineChart>
                                </ResponsiveContainer>
                            </div>
                        </div>
                    </div>
                ))}

                {filtered.length === 0 && (
                    <div className="card">
                        <div className="empty-state">
                            <div className="empty-state-icon"><Activity size={22} color="#94A3B8" /></div>
                            <div style={{ fontSize: 14, color: '#64748B' }}>No active predictions</div>
                            <div style={{ fontSize: 12, color: '#94A3B8', marginTop: 4 }}>All monitored services look healthy</div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
