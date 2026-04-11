// frontend/src/pages/Dashboard.tsx
import { useEffect, useState, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    AreaChart, Area, LineChart, Line, XAxis, YAxis, Tooltip,
    ResponsiveContainer, CartesianGrid, Legend
} from 'recharts';
import { AlertTriangle, Activity, Clock, TrendingUp, ChevronRight, Wifi, WifiOff, ArrowUpRight, ArrowDownRight, Minus, Globe, CheckCircle, XCircle, Download, BarChart2, History } from 'lucide-react';
import api from '../services/api';
import { useProject } from '../context/ProjectContext';

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
    const { selectedProject } = useProject();
    const [summary, setSummary] = useState<any>(null);
    const [incidents, setIncidents] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [wsConnected, setWsConnected] = useState(false);
    const [cpuData, setCpuData] = useState<any[]>([]);
    const [errorRateData, setErrorRateData] = useState<any[]>([]);
    const [realMetrics, setRealMetrics] = useState(false);
    const wsRef = useRef<WebSocket | null>(null);

    // Website monitor state
    const [websiteUrl, setWebsiteUrl] = useState('');
    const [websiteInput, setWebsiteInput] = useState('');
    const [liveMonitoring, setLiveMonitoring] = useState(false);
    const [websiteChecks, setWebsiteChecks] = useState<any[]>([]);
    const [websiteSaving, setWebsiteSaving] = useState(false);

    // Weekly summary state
    const [weeklySummary, setWeeklySummary] = useState<any>(null);
    const [weeklyLoading, setWeeklyLoading] = useState(false);

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
                const incParams: Record<string, any> = { limit: 8 };
                if (selectedProject) incParams.project_id = selectedProject.id;
                const [sumData, incData] = await Promise.all([
                    api.getSummary(),
                    api.getIncidents(incParams),
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
                    // Filter incoming WS incidents by selected project
                    if (!selectedProject || inc.repo_id === selectedProject.id) {
                        setIncidents(prev => [inc, ...prev.filter(i => i.incident_id !== inc.incident_id)].slice(0, 8));
                    }
                } catch { /* ignore */ }
            };
        } catch { /* websocket not available in this env */ }

        return () => wsRef.current?.close();
    }, [selectedProject?.id]);

    // Load website check history when project selected & monitoring active
    const fetchWebsiteChecks = useCallback(async () => {
        if (!selectedProject || !liveMonitoring) return;
        try {
            const data = await (api as any).get(`/api/v1/repositories/${selectedProject.id}/website-checks?limit=60`) as any;
            const checks = (data.checks || []).reverse().map((c: any) => ({
                t: new Date(c.checked_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                ms: c.response_time_ms ?? 0,
                up: c.is_up ? 1 : 0,
                status: c.status_code,
            }));
            setWebsiteChecks(checks);
        } catch { /* offline */ }
    }, [selectedProject, liveMonitoring]);

    useEffect(() => {
        if (!selectedProject) return;
        // Load website URL from repo data
        if (selectedProject.website_url) {
            setWebsiteUrl(selectedProject.website_url);
            setWebsiteInput(selectedProject.website_url);
        }
        setLiveMonitoring(selectedProject.is_live_monitoring_enabled ?? false);
    }, [selectedProject]);

    useEffect(() => {
        fetchWebsiteChecks();
        const interval = setInterval(fetchWebsiteChecks, 60000);
        return () => clearInterval(interval);
    }, [fetchWebsiteChecks]);

    // Load weekly summary
    useEffect(() => {
        setWeeklyLoading(true);
        (api as any).get('/api/v1/reports/weekly').then((d: any) => setWeeklySummary(d)).catch(() => { }).finally(() => setWeeklyLoading(false));
    }, []);

    const handleSaveWebsiteUrl = async () => {
        if (!selectedProject) return;
        const url = websiteInput.trim();
        if (!url) return;
        setWebsiteSaving(true);
        try {
            await (api as any).put(`/api/v1/repositories/${selectedProject.id}/website-url`, { website_url: url, is_live_monitoring_enabled: true });
            setWebsiteUrl(url);
            setLiveMonitoring(true);
            setTimeout(fetchWebsiteChecks, 2000);
        } catch { /* ignore */ } finally { setWebsiteSaving(false); }
    };

    const downloadWeeklySummary = () => {
        if (!weeklySummary) return;
        const s = weeklySummary;
        const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>PulseQ Weekly Summary</title>
<style>body{font-family:system-ui,sans-serif;max-width:800px;margin:40px auto;padding:20px;color:#0F172A}
h1{font-size:28px;font-weight:800;margin-bottom:4px}h2{font-size:16px;font-weight:700;margin-top:24px;margin-bottom:10px;color:#374151}
.meta{color:#64748B;font-size:13px;margin-bottom:24px}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:24px}
.card{background:#F8FAFC;border-radius:10px;padding:16px;border:1px solid #E2E8F0}
.card .val{font-size:28px;font-weight:800;color:#6366F1}
.card .lbl{font-size:11px;color:#94A3B8;font-weight:600;text-transform:uppercase;letter-spacing:.04em;margin-top:4px}
table{width:100%;border-collapse:collapse;margin-top:12px}
th{text-align:left;padding:8px 12px;font-size:11px;color:#94A3B8;font-weight:700;text-transform:uppercase;border-bottom:2px solid #E2E8F0}
td{padding:10px 12px;font-size:13px;border-bottom:1px solid #F1F5F9}
.badge{padding:2px 8px;border-radius:9999px;font-size:11px;font-weight:800}
.p1{background:#FEF2F2;color:#DC2626}.p2{background:#FFF7ED;color:#EA580C}
.p3{background:#FEF9C3;color:#CA8A04}.p4{background:#F0FDF4;color:#16A34A}
footer{margin-top:32px;font-size:11px;color:#94A3B8;border-top:1px solid #E2E8F0;padding-top:12px}
</style></head><body>
<h1>PulseQ Weekly Summary</h1>
<div class="meta">Period: ${new Date(s.week_start).toDateString()} — ${new Date(s.week_end).toDateString()}</div>
<div class="grid">
<div class="card"><div class="val">${s.total_incidents}</div><div class="lbl">Total Incidents</div></div>
<div class="card"><div class="val">${s.resolved_count}</div><div class="lbl">Resolved</div></div>
<div class="card"><div class="val">${s.avg_mttr_minutes ? Math.round(s.avg_mttr_minutes) + 'm' : '—'}</div><div class="lbl">Avg MTTR</div></div>
</div>
<h2>Incidents by Severity</h2><table><thead><tr><th>Severity</th><th>Count</th></tr></thead><tbody>
${Object.entries(s.by_severity || {}).map(([sev, cnt]) => `<tr><td><span class="badge ${sev.toLowerCase()}">${sev}</span></td><td>${cnt}</td></tr>`).join('')}</tbody></table>
<h2>Top Impacted Services</h2><table><thead><tr><th>Service</th><th>Incidents</th></tr></thead><tbody>
${(s.top_services || []).map((x: any) => `<tr><td>${x.service}</td><td>${x.count}</td></tr>`).join('')}</tbody></table>
<h2>All Incidents This Week</h2><table><thead><tr><th>Title</th><th>Severity</th><th>Status</th><th>MTTR</th></tr></thead><tbody>
${(s.incidents || []).map((i: any) => `<tr><td>${i.title}</td><td><span class="badge ${(i.severity || '').toLowerCase()}">${i.severity || ''}</span></td><td>${i.status || ''}</td><td>${i.mttr_minutes ? Math.round(i.mttr_minutes) + 'm' : '—'}</td></tr>`).join('')}</tbody></table>
<footer>Generated by PulseQ · ${new Date().toLocaleString()}</footer>
</body></html>`;
        const blob = new Blob([html], { type: 'text/html' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `neuralops-weekly-${new Date().toISOString().split('T')[0]}.html`;
        a.click();
        URL.revokeObjectURL(a.href);
    };

    const activeCount = (summary?.incidents_by_status &&
        ((summary.incidents_by_status['detected'] || 0) +
            (summary.incidents_by_status['investigating'] || 0) +
            (summary.incidents_by_status['remediating'] || 0))) || 0;
    const p1Count = summary?.active_incidents_by_severity?.['P1'] || 0;
    const mttr = summary?.avg_mttr_7d_minutes ? `${Math.round(summary.avg_mttr_7d_minutes)}m` : '—';
    const topAnomalies = summary?.top_anomalies || [];
    const lastCheck = websiteChecks.length > 0 ? websiteChecks[websiteChecks.length - 1] : null;

    return (
        <div className="animate-fade" style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                    <h1 style={{ fontSize: 22, fontWeight: 800, color: '#0F172A', letterSpacing: '-0.02em' }}>Operations Dashboard</h1>
                    <div style={{ fontSize: 13, color: '#64748B', marginTop: 3 }}>
                        Real-time SRE intelligence · {new Date().toLocaleTimeString()}
                        {selectedProject && <span style={{ marginLeft: 8, color: '#6366F1', fontWeight: 600 }}>· {selectedProject.name}</span>}
                    </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: wsConnected ? '#059669' : '#94A3B8', background: wsConnected ? '#ECFDF5' : '#F8FAFC', padding: '5px 12px', borderRadius: 9999, border: `1px solid ${wsConnected ? '#A7F3D0' : '#E2E8F0'}` }}>
                        {wsConnected ? <Wifi size={12} /> : <WifiOff size={12} />}
                        {wsConnected ? 'Live' : 'Connecting…'}
                    </div>
                    <button onClick={() => navigate('/incidents/history')} style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '5px 12px', borderRadius: 8, border: '1px solid #E2E8F0', background: '#F8FAFC', cursor: 'pointer', fontSize: 12, fontWeight: 600, color: '#374151' }}>
                        <History size={13} /> Incident History
                    </button>
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

            {/* Live Website Monitor */}
            <div className="card" style={{ padding: 20 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Globe size={16} color="#6366F1" />
                        <span style={{ fontWeight: 700, fontSize: 14, color: '#0F172A' }}>Live Website Monitor</span>
                        {liveMonitoring && lastCheck && (
                            <span style={{
                                display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, fontWeight: 600,
                                color: lastCheck.up ? '#059669' : '#DC2626',
                                background: lastCheck.up ? '#ECFDF5' : '#FEF2F2',
                                padding: '2px 8px', borderRadius: 9999
                            }}>
                                {lastCheck.up ? <CheckCircle size={11} /> : <XCircle size={11} />}
                                {lastCheck.up ? `UP · ${lastCheck.ms?.toFixed(0)}ms` : `DOWN · ${lastCheck.status || 'unreachable'}`}
                            </span>
                        )}
                    </div>
                    {websiteUrl && (
                        <a href={websiteUrl} target="_blank" rel="noreferrer" style={{ fontSize: 11, color: '#6366F1', textDecoration: 'none' }}>
                            {websiteUrl}
                        </a>
                    )}
                </div>
                <div style={{ display: 'flex', gap: 8, marginBottom: liveMonitoring ? 16 : 0 }}>
                    <input
                        value={websiteInput}
                        onChange={e => setWebsiteInput(e.target.value)}
                        placeholder={selectedProject ? `e.g. https://${selectedProject.name}.example.com` : 'Select a project first…'}
                        disabled={!selectedProject}
                        onKeyDown={e => e.key === 'Enter' && handleSaveWebsiteUrl()}
                        style={{
                            flex: 1, padding: '8px 12px', borderRadius: 8,
                            border: '1px solid #E2E8F0', fontSize: 12, outline: 'none',
                            background: selectedProject ? '#F8FAFC' : '#F1F5F9',
                        }}
                        onFocus={e => (e.target.style.border = '1px solid #6366F1')}
                        onBlur={e => (e.target.style.border = '1px solid #E2E8F0')}
                    />
                    <button
                        onClick={handleSaveWebsiteUrl}
                        disabled={!selectedProject || websiteSaving || !websiteInput.trim()}
                        style={{
                            padding: '8px 16px', borderRadius: 8,
                            background: 'linear-gradient(135deg,#6366F1,#3B82F6)',
                            border: 'none', color: '#fff', fontSize: 12, fontWeight: 700,
                            cursor: (!selectedProject || websiteSaving || !websiteInput.trim()) ? 'not-allowed' : 'pointer',
                            opacity: (!selectedProject || !websiteInput.trim()) ? 0.6 : 1,
                        }}
                    >
                        {websiteSaving ? 'Saving…' : 'Enable Live'}
                    </button>
                </div>

                {liveMonitoring && websiteChecks.length > 0 && (
                    <div>
                        <div style={{ fontSize: 11, color: '#94A3B8', fontWeight: 600, marginBottom: 8 }}>Response time — last 60 checks (ms)</div>
                        <ResponsiveContainer width="100%" height={120}>
                            <AreaChart data={websiteChecks}>
                                <defs>
                                    <linearGradient id="gWebsite" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#6366F1" stopOpacity={0.2} />
                                        <stop offset="95%" stopColor="#6366F1" stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                                <XAxis dataKey="t" tick={{ fontSize: 9, fill: '#94A3B8' }} interval={9} />
                                <YAxis tick={{ fontSize: 9, fill: '#94A3B8' }} tickFormatter={v => `${v}ms`} width={40} />
                                <Tooltip
                                    contentStyle={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: 8, fontSize: 11 }}
                                    formatter={(val: any, _: any, payload: any) => [
                                        `${Number(val).toFixed(0)}ms`,
                                        payload?.payload?.status ? `HTTP ${payload.payload.status}` : 'Response Time'
                                    ]}
                                />
                                <Area type="monotone" dataKey="ms" stroke="#6366F1" fill="url(#gWebsite)" strokeWidth={2} dot={(props: any) => {
                                    const { cx, cy, payload } = props;
                                    return <circle key={payload.t} cx={cx} cy={cy} r={3} fill={payload.up ? '#10B981' : '#EF4444'} stroke="#fff" strokeWidth={1} />;
                                }} />
                            </AreaChart>
                        </ResponsiveContainer>
                        <div style={{ display: 'flex', gap: 12, marginTop: 8, fontSize: 10, color: '#94A3B8' }}>
                            <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><div style={{ width: 8, height: 8, borderRadius: '50%', background: '#10B981' }} /> Up</span>
                            <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><div style={{ width: 8, height: 8, borderRadius: '50%', background: '#EF4444' }} /> Down</span>
                        </div>
                    </div>
                )}

                {liveMonitoring && websiteChecks.length === 0 && (
                    <div style={{ textAlign: 'center', padding: '20px 0', color: '#94A3B8', fontSize: 12 }}>
                        Waiting for first check (runs every 60 seconds)…
                    </div>
                )}
            </div>

            {/* Live graphs */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                <div className="card" style={{ padding: 20 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                        <div>
                            <div style={{ fontSize: 14, fontWeight: 700, color: '#0F172A' }}>CPU & Memory</div>
                            <div style={{ fontSize: 11, color: '#94A3B8', marginTop: 2 }}>
                                {realMetrics ? 'Live · PulseQ server (psutil)' : 'Demo · backend offline'}
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
                    <div style={{ display: 'flex', gap: 8 }}>
                        <button className="btn btn-secondary" onClick={() => navigate('/incidents/history')} style={{ fontSize: 12, padding: '6px 12px', display: 'flex', alignItems: 'center', gap: 4 }}>
                            <History size={12} /> History
                        </button>
                        <button className="btn btn-secondary" onClick={() => navigate('/incidents')} style={{ fontSize: 12, padding: '6px 12px' }}>
                            View all <ChevronRight size={12} />
                        </button>
                    </div>
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

            {/* Weekly Summary */}
            <div className="card" style={{ padding: 20 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <BarChart2 size={16} color="#6366F1" />
                        <span style={{ fontWeight: 700, fontSize: 14, color: '#0F172A' }}>Weekly Summary</span>
                        <span style={{ fontSize: 11, color: '#94A3B8' }}>Last 7 days</span>
                    </div>
                    <button
                        onClick={downloadWeeklySummary}
                        disabled={!weeklySummary || weeklyLoading}
                        style={{
                            display: 'flex', alignItems: 'center', gap: 6,
                            padding: '7px 14px', borderRadius: 8,
                            background: 'linear-gradient(135deg,#6366F1,#3B82F6)',
                            border: 'none', color: '#fff', fontSize: 12, fontWeight: 700,
                            cursor: (!weeklySummary || weeklyLoading) ? 'not-allowed' : 'pointer',
                            opacity: (!weeklySummary || weeklyLoading) ? 0.6 : 1,
                            boxShadow: '0 4px 12px rgba(99,102,241,0.3)',
                        }}
                    >
                        <Download size={13} /> Download Report
                    </button>
                </div>

                {weeklyLoading ? (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12 }}>
                        {[1, 2, 3, 4].map(i => <div key={i} className="skeleton" style={{ height: 70, borderRadius: 10 }} />)}
                    </div>
                ) : weeklySummary ? (
                    <div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12, marginBottom: 16 }}>
                            {[
                                { label: 'Total Incidents', value: weeklySummary.total_incidents, color: '#EF4444' },
                                { label: 'Resolved', value: weeklySummary.resolved_count, color: '#10B981' },
                                { label: 'Avg MTTR', value: weeklySummary.avg_mttr_minutes ? `${Math.round(weeklySummary.avg_mttr_minutes)}m` : '—', color: '#6366F1' },
                                { label: 'P1 Incidents', value: weeklySummary.by_severity?.['P1'] ?? 0, color: '#DC2626' },
                            ].map(({ label, value, color }) => (
                                <div key={label} style={{ background: '#F8FAFC', borderRadius: 10, padding: '12px 14px', border: '1px solid #E2E8F0' }}>
                                    <div style={{ fontSize: 22, fontWeight: 800, color, lineHeight: 1 }}>{value}</div>
                                    <div style={{ fontSize: 10, color: '#94A3B8', fontWeight: 600, marginTop: 4, textTransform: 'uppercase', letterSpacing: '0.04em' }}>{label}</div>
                                </div>
                            ))}
                        </div>
                        {(weeklySummary.by_severity && Object.keys(weeklySummary.by_severity).length > 0) && (
                            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                                {Object.entries(weeklySummary.by_severity).map(([sev, cnt]: any) => (
                                    <div key={sev} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '4px 12px', borderRadius: 9999, background: sev === 'P1' ? '#FEF2F2' : sev === 'P2' ? '#FFF7ED' : sev === 'P3' ? '#FEF9C3' : '#F0FDF4' }}>
                                        <span style={{ fontWeight: 800, fontSize: 11, color: sev === 'P1' ? '#DC2626' : sev === 'P2' ? '#EA580C' : sev === 'P3' ? '#CA8A04' : '#16A34A' }}>{sev}</span>
                                        <span style={{ fontSize: 12, color: '#374151', fontWeight: 600 }}>{cnt}</span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                ) : (
                    <div style={{ textAlign: 'center', padding: '20px 0', color: '#94A3B8', fontSize: 12 }}>No data available for this week.</div>
                )}
            </div>
        </div>
    );
}
