// frontend/src/pages/Dashboard.tsx
import { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    AreaChart, Area, LineChart, Line, XAxis, YAxis, Tooltip,
    ResponsiveContainer, CartesianGrid, Legend
} from 'recharts';
import { AlertTriangle, Activity, Clock, TrendingUp, ChevronRight, Wifi, WifiOff, ArrowUpRight, ArrowDownRight, Minus } from 'lucide-react';
import api from '../services/api';

const SEVERITY_COLOR: Record<string, string> = {
    P1: '#EF4444', P2: '#F97316', P3: '#F59E0B', P4: '#6366F1',
};

const STATUS_STYLE: Record<string, { bg: string; color: string; label: string }> = {
    detected: { bg: '#FEF2F2', color: '#DC2626', label: 'Detected' },
    investigating: { bg: '#FFFBEB', color: '#D97706', label: 'Investigating' },
    remediating: { bg: '#FFF7ED', color: '#EA580C', label: 'Remediating' },
    resolved: { bg: '#ECFDF5', color: '#059669', label: 'Resolved' },
    false_positive: { bg: '#F8FAFC', color: '#64748B', label: 'False Positive' },
};

function MetricCard({ label, value, sub, color, icon: Icon, trend }: any) {
    return (
        <div className="card" style={{ padding: '20px 24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: '#94A3B8', letterSpacing: '0.06em', textTransform: 'uppercase' }}>{label}</div>
                <div style={{
                    width: 34, height: 34, borderRadius: 10,
                    background: `${color}14`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                    <Icon size={16} color={color} />
                </div>
            </div>
            <div style={{ fontSize: 30, fontWeight: 800, color: '#0F172A', letterSpacing: '-0.02em', lineHeight: 1 }}>{value}</div>
            {sub && <div style={{ fontSize: 12, color: '#64748B', marginTop: 8, display: 'flex', alignItems: 'center', gap: 4 }}>
                {trend === 'up' && <ArrowUpRight size={12} color="#EF4444" />}
                {trend === 'down' && <ArrowDownRight size={12} color="#10B981" />}
                {trend === 'neutral' && <Minus size={12} color="#94A3B8" />}
                {sub}
            </div>}
        </div>
    );
}

function StatusPill({ status }: { status: string }) {
    const s = STATUS_STYLE[status] || { bg: '#F8FAFC', color: '#64748B', label: status };
    return (
        <span style={{
            fontSize: 11, padding: '3px 10px', borderRadius: 9999,
            background: s.bg, color: s.color, fontWeight: 600,
        }}>{s.label}</span>
    );
}

// Generate synthetic live metric data for demonstration
function generateMetricPoint(base: number, noise: number = 5): number {
    return Math.max(0, Math.min(100, base + (Math.random() - 0.5) * noise * 2));
}

export default function Dashboard() {
    const navigate = useNavigate();
    const [summary, setSummary] = useState<any>(null);
    const [incidents, setIncidents] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [wsConnected, setWsConnected] = useState(false);
    const [cpuData, setCpuData] = useState<any[]>([]);
    const [errorRateData, setErrorRateData] = useState<any[]>([]);
    const [realMetrics, setRealMetrics] = useState(false);
    const wsRef = useRef<WebSocket | null>(null);

    // Load real system metrics from psutil (falls back to synthetic if unavailable)
    useEffect(() => {
        async function loadMetrics() {
            try {
                const data = await api.getSystemMetrics(30) as any;
                const history: any[] = data.history || [];
                if (history.length > 0) {
                    setRealMetrics(true);
                    const cpu = history.map((s: any) => ({
                        t: new Date(s.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
                        'cpu': s.cpu_percent || 0,
                        'memory': s.memory_percent || 0,
                    }));
                    setCpuData(cpu);
                    return;
                }
            } catch { /* API not running, use synthetic */ }
            // Synthetic fallback
            const now = Date.now();
            const cpu: any[] = []; const err: any[] = [];
            for (let i = 29; i >= 0; i--) {
                const t = new Date(now - i * 10000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                cpu.push({ t, 'cpu': generateMetricPoint(45, 8), 'memory': generateMetricPoint(62, 5) });
                err.push({ t, '2xx': generateMetricPoint(88, 3), '4xx': generateMetricPoint(8, 2), '5xx': generateMetricPoint(2, 1) });
            }
            setCpuData(cpu); setErrorRateData(err);
        }
        loadMetrics();
        const interval = setInterval(async () => {
            try {
                const data = await api.getSystemMetrics(1) as any;
                const latest = data.latest;
                if (latest?.cpu_percent !== undefined) {
                    setRealMetrics(true);
                    const t = new Date(latest.timestamp || Date.now()).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                    setCpuData(prev => [...prev.slice(-29), { t, cpu: latest.cpu_percent, memory: latest.memory_percent }]);
                    return;
                }
            } catch { /* ignore */ }
            const t = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            setCpuData(prev => [...prev.slice(-29), { t, cpu: generateMetricPoint(45, 8), memory: generateMetricPoint(62, 5) }]);
            setErrorRateData(prev => [...prev.slice(-29), { t, '2xx': generateMetricPoint(88, 3), '4xx': generateMetricPoint(8, 2), '5xx': generateMetricPoint(2, 1) }]);
        }, 10000);
        return () => clearInterval(interval);
    }, []);

    useEffect(() => {
        async function load() {
            try {
                const [sumData, incData] = await Promise.all([
                    api.getSummary(),
                    api.getIncidents({ limit: 8 }),
                ]);
                setSummary(sumData);
                setIncidents(incData.incidents);
            } catch {
                // API might not be running locally — show demo state
            } finally { setLoading(false); }
        }
        load();

        // WebSocket for live incident updates
        try {
            const wsBase = (import.meta.env.VITE_API_URL || 'http://localhost:8080').replace(/^http/, 'ws');
            const token = localStorage.getItem('neuralops_token');
            const ws = new WebSocket(`${wsBase}/ws/incidents?token=${token}`);
            wsRef.current = ws;
            ws.onopen = () => setWsConnected(true);
            ws.onclose = () => setWsConnected(false);
            ws.onerror = () => setWsConnected(false);
            ws.onmessage = (e) => {
                try {
                    const inc = JSON.parse(e.data);
                    setIncidents(prev => [inc, ...prev.filter(i => i.incident_id !== inc.incident_id)].slice(0, 8));
                } catch { /* ignore */ }
            };
        } catch { /* websocket not available in this env */ }

        return () => wsRef.current?.close();
    }, []);

    const activeCount = (summary?.incidents_by_status &&
        ((summary.incidents_by_status['detected'] || 0) +
            (summary.incidents_by_status['investigating'] || 0) +
            (summary.incidents_by_status['remediating'] || 0))) || 0;
    const p1Count = summary?.active_incidents_by_severity?.['P1'] || 0;
    const mttr = summary?.avg_mttr_7d_minutes ? `${Math.round(summary.avg_mttr_7d_minutes)}m` : '—';
    const topAnomalies = summary?.top_anomalies || [];

    return (
        <div className="animate-fade" style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                    <h1 style={{ fontSize: 22, fontWeight: 800, color: '#0F172A', letterSpacing: '-0.02em' }}>Operations Dashboard</h1>
                    <div style={{ fontSize: 13, color: '#64748B', marginTop: 3 }}>
                        Real-time SRE intelligence · {new Date().toLocaleTimeString()}
                    </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: wsConnected ? '#059669' : '#94A3B8', background: wsConnected ? '#ECFDF5' : '#F8FAFC', padding: '5px 12px', borderRadius: 9999, border: `1px solid ${wsConnected ? '#A7F3D0' : '#E2E8F0'}` }}>
                    {wsConnected ? <Wifi size={12} /> : <WifiOff size={12} />}
                    {wsConnected ? 'Live' : 'Connecting…'}
                </div>
            </div>

            {/* Metric cards */}
            {loading ? (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
                    {[1, 2, 3, 4].map(i => <div key={i} className="skeleton" style={{ height: 104, borderRadius: 14 }} />)}
                </div>
            ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
                    <MetricCard label="Active Incidents" value={activeCount} color={activeCount > 0 ? '#EF4444' : '#10B981'} icon={AlertTriangle} sub={`${p1Count} critical (P1)`} trend={activeCount > 0 ? 'up' : 'neutral'} />
                    <MetricCard label="Top Anomaly Score" value={topAnomalies[0] ? topAnomalies[0].anomaly_score?.toFixed(2) : '—'} color="#F97316" icon={Activity} sub={topAnomalies[0]?.service_name || 'No anomalies'} trend="neutral" />
                    <MetricCard label="Avg MTTR (7d)" value={mttr} color="#6366F1" icon={Clock} sub="Mean time to resolve" trend="down" />
                    <MetricCard label="Anomalies" value={topAnomalies.length} color="#3B82F6" icon={TrendingUp} sub="In current window" trend="neutral" />
                </div>
            )}

            {/* Live graphs */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                <div className="card" style={{ padding: 20 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                        <div>
                            <div style={{ fontSize: 14, fontWeight: 700, color: '#0F172A' }}>CPU & Memory</div>
                            <div style={{ fontSize: 11, color: '#94A3B8', marginTop: 2 }}>
                                {realMetrics ? 'Live · NeuralOps server (psutil)' : 'Demo · backend offline'}
                            </div>
                        </div>
                        <div style={{ fontSize: 11, color: realMetrics ? '#059669' : '#94A3B8', display: 'flex', alignItems: 'center', gap: 4 }}>
                            <div style={{ width: 6, height: 6, borderRadius: '50%', background: realMetrics ? '#10B981' : '#94A3B8' }} />
                            {realMetrics ? 'Real data' : 'Demo'}
                        </div>
                    </div>
                    <ResponsiveContainer width="100%" height={160}>
                        <LineChart data={cpuData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                            <XAxis dataKey="t" tick={{ fontSize: 9.5, fill: '#94A3B8' }} interval={9} />
                            <YAxis domain={[0, 100]} tick={{ fontSize: 9.5, fill: '#94A3B8' }} tickFormatter={v => `${v}%`} width={35} />
                            <Tooltip contentStyle={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: 8, fontSize: 11 }} />
                            <Line type="monotone" dataKey="cpu" stroke="#6366F1" strokeWidth={2} dot={false} name="CPU %" />
                            <Line type="monotone" dataKey="memory" stroke="#10B981" strokeWidth={2} dot={false} name="Memory %" />
                            <Legend wrapperStyle={{ fontSize: 11 }} />
                        </LineChart>
                    </ResponsiveContainer>
                </div>

                {/* Error Rate */}
                <div className="card" style={{ padding: 20 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                        <div>
                            <div style={{ fontSize: 14, fontWeight: 700, color: '#0F172A' }}>Request Status</div>
                            <div style={{ fontSize: 11, color: '#94A3B8', marginTop: 2 }}>HTTP status distribution</div>
                        </div>
                    </div>
                    <ResponsiveContainer width="100%" height={160}>
                        <AreaChart data={errorRateData}>
                            <defs>
                                <linearGradient id="g2xx" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#10B981" stopOpacity={0.15} />
                                    <stop offset="95%" stopColor="#10B981" stopOpacity={0} />
                                </linearGradient>
                                <linearGradient id="g5xx" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#EF4444" stopOpacity={0.2} />
                                    <stop offset="95%" stopColor="#EF4444" stopOpacity={0} />
                                </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                            <XAxis dataKey="t" tick={{ fontSize: 9.5, fill: '#94A3B8' }} interval={9} />
                            <YAxis domain={[0, 100]} tick={{ fontSize: 9.5, fill: '#94A3B8' }} tickFormatter={v => `${v}%`} width={35} />
                            <Tooltip contentStyle={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: 8, fontSize: 11 }} />
                            <Area type="monotone" dataKey="2xx" stroke="#10B981" fill="url(#g2xx)" strokeWidth={2} name="2xx Success" />
                            <Area type="monotone" dataKey="4xx" stroke="#F59E0B" strokeWidth={1.5} dot={false} fill="none" name="4xx Client" />
                            <Area type="monotone" dataKey="5xx" stroke="#EF4444" fill="url(#g5xx)" strokeWidth={2} name="5xx Error" />
                            <Legend wrapperStyle={{ fontSize: 11 }} />
                        </AreaChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* Recent incidents table */}
            <div className="card" style={{ overflow: 'hidden' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 20px', borderBottom: '1px solid #E2E8F0' }}>
                    <div style={{ fontSize: 14, fontWeight: 700, color: '#0F172A' }}>Recent Incidents</div>
                    <button className="btn btn-secondary" onClick={() => navigate('/incidents')} style={{ fontSize: 12, padding: '6px 12px' }}>
                        View all <ChevronRight size={12} />
                    </button>
                </div>
                {loading ? (
                    <div style={{ padding: 24 }}>
                        {[1, 2, 3].map(i => <div key={i} className="skeleton" style={{ height: 40, borderRadius: 8, marginBottom: 10 }} />)}
                    </div>
                ) : (
                    <table className="data-table">
                        <thead>
                            <tr>
                                {['Severity', 'Title', 'Service', 'ML Score', 'Status', 'Detected'].map(h => (
                                    <th key={h}>{h}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {incidents.map(inc => (
                                <tr key={inc.incident_id} onClick={() => navigate(`/incidents/${inc.incident_id}`)}>
                                    <td><span className={`badge badge-${inc.severity?.toLowerCase()}`}>{inc.severity}</span></td>
                                    <td style={{ fontWeight: 500, color: '#0F172A', maxWidth: 300 }}>
                                        <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{inc.title}</div>
                                        <div style={{ fontSize: 11, color: '#94A3B8', marginTop: 2 }}>{inc.environment} · {inc.cloud_provider}</div>
                                    </td>
                                    <td style={{ color: '#64748B' }}>{inc.primary_service}</td>
                                    <td>
                                        <span style={{ fontWeight: 600, color: (inc.peak_anomaly_score || 0) > 0.8 ? '#EF4444' : (inc.peak_anomaly_score || 0) > 0.6 ? '#F59E0B' : '#10B981', fontFamily: 'monospace', fontSize: 12 }}>
                                            {(inc.peak_anomaly_score || 0).toFixed(3)}
                                        </span>
                                    </td>
                                    <td><StatusPill status={inc.status} /></td>
                                    <td style={{ color: '#64748B', fontSize: 12 }}>{new Date(inc.detected_at).toLocaleString()}</td>
                                </tr>
                            ))}
                            {incidents.length === 0 && !loading && (
                                <tr><td colSpan={6}>
                                    <div className="empty-state">
                                        <div className="empty-state-icon"><Activity size={22} color="#94A3B8" /></div>
                                        <div style={{ fontSize: 14, color: '#64748B' }}>No active incidents detected</div>
                                        <div style={{ fontSize: 12, color: '#94A3B8', marginTop: 4 }}>All systems operating normally</div>
                                    </div>
                                </td></tr>
                            )}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
}
