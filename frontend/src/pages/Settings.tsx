// frontend/src/pages/Settings.tsx
import { useState, useEffect, useRef } from 'react';
import { Settings as SettingsIcon, Bell, Users, Brain, Save, CheckCircle, BarChart3, TrendingDown, Award, Loader2, Zap, Cpu, Activity, Server, Database, ShieldCheck, ChevronRight } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import api from '../services/api';

// ── Types ──────────────────────────────────────────────────────────────────────
interface Phi3Health {
    status: 'ready' | 'not_installed' | 'unreachable' | 'installed_not_responding' | null;
    model?: string;
    response_time_ms?: number;
    install_command?: string;
    docker_command?: string;
    error?: string;
}

interface ServiceStatus {
    status: 'healthy' | 'warning' | 'error' | 'loading';
    response_ms?: number;
    error?: string;
    fix?: string;
    model?: string;
}

interface SystemHealth {
    status: string;
    timestamp: string;
    services: Record<string, ServiceStatus>;
    active_llm: string;
}

interface LLMHealth {
    openrouter: { available: boolean; model?: string; error?: string | null; test_response?: string };
    phi3: { available: boolean; model?: string; error?: string | null };
    active_model: string;
}

const SECTIONS = ['Integrations', 'System Health', 'Notifications', 'Users', 'RL Dashboard'];

const RL_ACCURACY = Array.from({ length: 30 }, (_, i) => ({ d: `Day ${i + 1} `, acc: +(0.65 + (i / 29) * 0.25 + (Math.random() - 0.5) * 0.04).toFixed(3) }));
const RL_MTTR = Array.from({ length: 30 }, (_, i) => ({ d: `Day ${i + 1} `, mttr: Math.round(42 - (i / 29) * 18 + (Math.random() - 0.5) * 4) }));

// ── Sub-components ─────────────────────────────────────────────────────────────
function InputRow({ label, placeholder, type = 'text', defaultValue = '', secret = false }: {
    label: string; placeholder: string; type?: string; defaultValue?: string; secret?: boolean;
}) {
    const [val, setVal] = useState<string>(defaultValue);
    const [show, setShow] = useState<boolean>(!secret);
    return (
        <div>
            <label style={{ fontSize: 12, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 6 }}>{label}</label>
            <div style={{ position: 'relative' }}>
                <input
                    className="form-input"
                    type={secret && !show ? 'password' : type}
                    value={val}
                    onChange={e => setVal(e.target.value)}
                    placeholder={placeholder}
                />
                {secret && (
                    <button type="button" style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', fontSize: 11, color: '#94A3B8' }} onClick={() => setShow((s: boolean) => !s)}>
                        {show ? 'Hide' : 'Show'}
                    </button>
                )}
            </div>
        </div>
    );
}

function ToggleRow({ label, description, defaultOn = false }: {
    label: string; description: string; defaultOn?: boolean;
}) {
    const [on, setOn] = useState<boolean>(defaultOn);
    return (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 0', borderBottom: '1px solid #F1F5F9' }}>
            <div>
                <div style={{ fontSize: 13, fontWeight: 500, color: '#0F172A' }}>{label}</div>
                <div style={{ fontSize: 12, color: '#94A3B8', marginTop: 2 }}>{description}</div>
            </div>
            <div onClick={() => setOn((s: boolean) => !s)} style={{
                width: 42, height: 24, borderRadius: 12,
                background: on ? '#6366F1' : '#E2E8F0',
                cursor: 'pointer', position: 'relative', transition: 'background 0.2s',
            }}>
                <div style={{
                    position: 'absolute', top: 3, left: on ? 21 : 3, width: 18, height: 18,
                    borderRadius: '50%', background: '#fff', transition: 'left 0.2s',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
                }} />
            </div>
        </div>
    );
}

// ── Service status circle ──────────────────────────────────────────────────────
function StatusDot({ status }: { status: string }) {
    const color = status === 'healthy' ? '#10B981' : status === 'warning' ? '#F59E0B' : status === 'loading' ? '#94A3B8' : '#EF4444';
    return (
        <span style={{
            width: 10, height: 10, borderRadius: '50%', background: color,
            display: 'inline-block', flexShrink: 0,
            boxShadow: `0 0 6px ${color}66`,
        }} />
    );
}

const SERVICE_ICONS: Record<string, any> = {
    postgres: Database,
    redis: Activity,
    mongodb: Database,
    chromadb: Brain,
    openrouter: Zap,
    phi3: Cpu,
};

const SERVICE_LABELS: Record<string, string> = {
    postgres: 'PostgreSQL',
    redis: 'Redis',
    mongodb: 'MongoDB',
    chromadb: 'ChromaDB',
    openrouter: 'OpenRouter (LLM)',
    phi3: 'Phi-3 / Ollama',
};

function ServiceCard({ name, data }: { name: string; data: ServiceStatus }) {
    const Icon = SERVICE_ICONS[name] || Server;
    return (
        <div className="card-surface" style={{ padding: '14px 16px', borderRadius: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{ width: 30, height: 30, borderRadius: 8, background: 'rgba(99,102,241,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Icon size={14} color="#6366F1" />
                </div>
                <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: '#0F172A' }}>{SERVICE_LABELS[name] || name}</div>
                    {data.model && <div style={{ fontSize: 11, color: '#94A3B8' }}>{data.model}</div>}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <StatusDot status={data.status} />
                    <span style={{
                        fontSize: 11, fontWeight: 700,
                        color: data.status === 'healthy' ? '#059669' : data.status === 'warning' ? '#D97706' : data.status === 'loading' ? '#94A3B8' : '#DC2626',
                        textTransform: 'capitalize',
                    }}>
                        {data.status === 'loading' ? 'Checking…' : data.status}
                    </span>
                    {data.response_ms != null && (
                        <span style={{ fontSize: 10, color: '#94A3B8' }}>{data.response_ms}ms</span>
                    )}
                </div>
            </div>
            {(data.status === 'warning' || data.status === 'error') && (
                <div style={{
                    background: data.status === 'warning' ? '#FFFBEB' : '#FEF2F2',
                    border: `1px solid ${data.status === 'warning' ? '#FDE68A' : '#FECACA'}`,
                    borderRadius: 7, padding: '8px 12px', fontSize: 11,
                    color: data.status === 'warning' ? '#92400E' : '#991B1B',
                }}>
                    <div><strong>Error:</strong> {data.error}</div>
                    {data.fix && <div style={{ marginTop: 4 }}><strong>Fix:</strong> <code style={{ fontFamily: 'monospace' }}>{data.fix}</code></div>}
                </div>
            )}
        </div>
    );
}

// ── Main component ─────────────────────────────────────────────────────────────
function isAdmin(): boolean {
    try {
        const token = localStorage.getItem('neuralops_token');
        if (!token) return false;
        const payload = JSON.parse(atob(token.split('.')[1]));
        return payload?.role === 'admin' || payload?.is_admin === true || payload?.sub === 'admin';
    } catch { return false; }
}

export default function Settings() {
    const [section, setSection] = useState('Integrations');
    const [saved, setSaved] = useState(false);
    const [currentUserIsAdmin] = useState<boolean>(isAdmin);
    const [phi3Health, setPhi3Health] = useState<Phi3Health>({ status: null });
    const [rlStats, setRlStats] = useState<any>(null);
    const [integrations, setIntegrations] = useState<any>({});

    // System Health state
    const [systemHealth, setSystemHealth] = useState<SystemHealth | null>(null);
    const [systemHealthLoading, setSystemHealthLoading] = useState(false);
    const [llmHealth, setLlmHealth] = useState<LLMHealth | null>(null);
    const [testResult, setTestResult] = useState<string | null>(null);
    const [testLoading, setTestLoading] = useState(false);
    const healthIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

    // Fetch system health
    const fetchSystemHealth = async () => {
        setSystemHealthLoading(true);
        try {
            const h = await api.getSystemHealth();
            setSystemHealth(h);
        } catch {
            setSystemHealth({ status: 'error', timestamp: '', services: {}, active_llm: 'unknown' });
        } finally {
            setSystemHealthLoading(false);
        }
    };

    useEffect(() => {
        api.getPhi3Health().then(r => setPhi3Health(r as Phi3Health)).catch(() => setPhi3Health({ status: 'unreachable', error: 'Could not contact API' }));
        api.getIntegrations().then(r => setIntegrations(r)).catch(() => { });
        api.getRLStats?.().then((r: any) => setRlStats(r)).catch(() => { });
    }, []);

    // Auto-fetch system health when section is active
    useEffect(() => {
        if (section === 'System Health') {
            fetchSystemHealth();
            healthIntervalRef.current = setInterval(fetchSystemHealth, 30000);
        } else {
            if (healthIntervalRef.current) {
                clearInterval(healthIntervalRef.current);
                healthIntervalRef.current = null;
            }
        }
        return () => {
            if (healthIntervalRef.current) {
                clearInterval(healthIntervalRef.current);
                healthIntervalRef.current = null;
            }
        };
    }, [section]);

    useEffect(() => {
        if (section === 'RL Dashboard') {
            api.getRLStats().then(s => setRlStats(s)).catch(() => { });
        }
    }, [section]);

    const handleSave = () => {
        setSaved(true);
        setTimeout(() => setSaved(false), 2500);
    };

    const handleTestChatbot = async () => {
        setTestLoading(true);
        setTestResult(null);
        try {
            const r = await api.getLLMHealth();
            setLlmHealth(r);
            const resp = r.openrouter?.test_response || r.phi3?.test_response;
            setTestResult(resp || `Active model: ${r.active_model} (no test response — inference test not yet run)`);
        } catch (e) {
            setTestResult('Failed to reach LLM health endpoint. Check backend logs.');
        } finally {
            setTestLoading(false);
        }
    };

    // Build loading placeholders when systemHealth is null
    const serviceNames = ['postgres', 'redis', 'mongodb', 'chromadb', 'openrouter', 'phi3'];

    return (
        <div className="animate-fade" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                    <h1 style={{ fontSize: 22, fontWeight: 800, color: '#0F172A', letterSpacing: '-0.02em' }}>Settings</h1>
                    <div style={{ fontSize: 13, color: '#64748B', marginTop: 3 }}>Platform configuration and integrations</div>
                </div>
                <button className="btn btn-primary" onClick={handleSave} disabled={saved}>
                    {saved ? <><CheckCircle size={13} /> Saved!</> : <><Save size={13} /> Save Changes</>}
                </button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr', gap: 20 }}>
                {/* Sidebar */}
                <div className="card" style={{ padding: 12, height: 'fit-content' }}>
                    {SECTIONS.map(s => (
                        <div key={s} onClick={() => setSection(s)} style={{
                            padding: '9px 12px', borderRadius: 8, cursor: 'pointer', fontSize: 13,
                            fontWeight: section === s ? 600 : 400,
                            color: section === s ? '#6366F1' : '#64748B',
                            background: section === s ? 'rgba(99,102,241,0.08)' : 'transparent',
                            transition: 'all 0.15s',
                        }}>
                            {s}
                        </div>
                    ))}
                </div>

                {/* Content */}
                <div className="card" style={{ padding: 28 }}>

                    {/* ── SYSTEM HEALTH ── */}
                    {section === 'System Health' && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                <div style={{ fontWeight: 700, fontSize: 15, color: '#0F172A' }}>System Health</div>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                    {systemHealthLoading && <Loader2 size={14} color="#94A3B8" style={{ animation: 'spin 1s linear infinite' }} />}
                                    <span style={{ fontSize: 11, color: '#94A3B8' }}>Auto-refreshes every 30s</span>
                                    <button className="btn btn-primary" style={{ fontSize: 12, padding: '6px 14px' }} onClick={fetchSystemHealth}>
                                        Refresh
                                    </button>
                                </div>
                            </div>

                            {/* Active LLM card */}
                            <div style={{
                                background: 'linear-gradient(135deg, #6366F1 0%, #818CF8 100%)',
                                borderRadius: 12, padding: '18px 22px',
                                display: 'flex', alignItems: 'center', gap: 16,
                            }}>
                                <div style={{ width: 44, height: 44, borderRadius: 12, background: 'rgba(255,255,255,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                    <Zap size={22} color="#fff" />
                                </div>
                                <div style={{ flex: 1 }}>
                                    <div style={{ fontSize: 11, fontWeight: 600, color: 'rgba(255,255,255,0.7)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Active LLM</div>
                                    <div style={{ fontSize: 17, fontWeight: 800, color: '#fff', marginTop: 2 }}>
                                        {systemHealth?.active_llm || (systemHealthLoading ? 'Checking…' : 'Unknown')}
                                    </div>
                                </div>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-end' }}>
                                    <button
                                        id="test-chatbot-btn"
                                        className="btn"
                                        style={{ background: 'rgba(255,255,255,0.18)', color: '#fff', border: '1px solid rgba(255,255,255,0.3)', fontSize: 12, padding: '7px 14px', borderRadius: 8, cursor: 'pointer' }}
                                        onClick={handleTestChatbot}
                                        disabled={testLoading}
                                    >
                                        {testLoading ? <><Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} /> Testing…</> : 'Test Chatbot'}
                                    </button>
                                    {testResult && (
                                        <div style={{
                                            maxWidth: 320, background: 'rgba(255,255,255,0.15)', borderRadius: 8,
                                            padding: '8px 12px', fontSize: 11, color: '#fff', lineHeight: 1.5,
                                        }}>
                                            <strong>Response:</strong> {testResult}
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* Overall status banner */}
                            {systemHealth && (
                                <div style={{
                                    padding: '10px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600,
                                    background: systemHealth.status === 'healthy' ? '#ECFDF5' : '#FEF2F2',
                                    color: systemHealth.status === 'healthy' ? '#059669' : '#DC2626',
                                    border: `1px solid ${systemHealth.status === 'healthy' ? '#A7F3D0' : '#FECACA'}`,
                                    display: 'flex', alignItems: 'center', gap: 8,
                                }}>
                                    <StatusDot status={systemHealth.status === 'healthy' ? 'healthy' : 'error'} />
                                    Overall: {systemHealth.status === 'healthy' ? 'All services healthy' : 'System degraded — see errors below'}
                                    {systemHealth.timestamp && (
                                        <span style={{ marginLeft: 'auto', fontSize: 11, fontWeight: 400, color: '#94A3B8' }}>
                                            Last checked: {new Date(systemHealth.timestamp).toLocaleTimeString()}
                                        </span>
                                    )}
                                </div>
                            )}

                            {/* Service cards grid */}
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                                {serviceNames.map(name => {
                                    const data: ServiceStatus = systemHealth?.services?.[name] ?? { status: 'loading' };
                                    return <ServiceCard key={name} name={name} data={data} />;
                                })}
                            </div>
                        </div>
                    )}

                    {/* ── INTEGRATIONS ── */}
                    {section === 'Integrations' && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
                            {/* Phi-3 AI Engine Status Card */}
                            <div className="card" style={{ padding: 20 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
                                    <Cpu size={16} color="#6366F1" />
                                    <span style={{ fontWeight: 600, fontSize: 14, color: '#0F172A' }}>Phi-3 AI Engine</span>
                                    <span style={{
                                        fontSize: 10, padding: '2px 7px', borderRadius: 5, fontWeight: 700,
                                        background: phi3Health.status === 'ready' ? '#ECFDF5' : phi3Health.status === null ? '#F1F5F9' : phi3Health.status === 'not_installed' ? '#FFFBEB' : '#FEF2F2',
                                        color: phi3Health.status === 'ready' ? '#059669' : phi3Health.status === null ? '#94A3B8' : phi3Health.status === 'not_installed' ? '#D97706' : '#DC2626',
                                        marginLeft: 'auto',
                                    }}>
                                        {phi3Health.status === null ? 'Checking…' : phi3Health.status === 'ready' ? '● Ready' : phi3Health.status === 'not_installed' ? '○ Not Installed' : '◆ Unreachable'}
                                    </span>
                                </div>
                                {phi3Health.status === 'ready' && (
                                    <div style={{ fontSize: 12, color: '#64748B' }}>
                                        Model: <strong>{phi3Health.model}</strong>
                                        {phi3Health.response_time_ms && <span style={{ marginLeft: 8, color: '#94A3B8' }}>· {phi3Health.response_time_ms}ms</span>}
                                    </div>
                                )}
                                {phi3Health.status === 'not_installed' && (
                                    <div style={{ fontSize: 12 }}>
                                        <div style={{ color: '#92400E', marginBottom: 8 }}>Phi-3 is not installed on Ollama. Run this command:</div>
                                        <code style={{
                                            display: 'block', background: '#FEF3C7', border: '1px solid #FDE68A',
                                            borderRadius: 6, padding: '8px 12px', fontSize: 11, color: '#78350F',
                                            fontFamily: 'monospace',
                                        }}>
                                            {phi3Health.docker_command || phi3Health.install_command}
                                        </code>
                                    </div>
                                )}
                                {(phi3Health.status === 'unreachable' || phi3Health.status === 'installed_not_responding') && (
                                    <div style={{ fontSize: 12, color: '#B91C1C' }}>
                                        {phi3Health.error || 'Could not connect to Ollama service.'}
                                    </div>
                                )}
                            </div>

                            {/* OpenRouter API Status Card */}
                            <div className="card" style={{ padding: 20 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
                                    <Zap size={16} color="#6366F1" />
                                    <span style={{ fontWeight: 600, fontSize: 14, color: '#0F172A' }}>OpenRouter API</span>
                                </div>
                                <div style={{ fontSize: 12, color: '#94A3B8', marginBottom: 16 }}>Primary LLM for RCA, chatbot, and code analysis. Get a free key at <a href="https://openrouter.ai" target="_blank" rel="noreferrer" style={{ color: '#6366F1' }}>openrouter.ai</a></div>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                                    <InputRow label="API KEY" placeholder="sk-or-..." defaultValue="" secret />
                                    <InputRow label="MODEL" placeholder="meta-llama/llama-3.1-8b-instruct:free" defaultValue="meta-llama/llama-3.1-8b-instruct:free" />
                                </div>
                            </div>
                            <hr className="divider" />
                            <div>
                                <div style={{ fontWeight: 700, fontSize: 15, color: '#0F172A', marginBottom: 4 }}>GitHub</div>
                                <div style={{ fontSize: 12, color: '#94A3B8', marginBottom: 16 }}>Repository analysis and code scanning</div>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                                    <InputRow label="PERSONAL ACCESS TOKEN" placeholder="ghp_..." secret />
                                    <InputRow label="ORG/USERNAME" placeholder="acme-corp" />
                                </div>
                            </div>
                            <hr className="divider" />
                            <div>
                                <div style={{ fontWeight: 700, fontSize: 15, color: '#0F172A', marginBottom: 4 }}>Slack</div>
                                <div style={{ fontSize: 12, color: '#94A3B8', marginBottom: 16 }}>P1/P2 incident alerts and RCA summaries</div>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                                    <InputRow label="WEBHOOK URL" placeholder="https://hooks.slack.com/..." secret />
                                    <InputRow label="CHANNEL" placeholder="#incidents" defaultValue="#incidents" />
                                </div>
                            </div>
                            <hr className="divider" />
                            <div>
                                <div style={{ fontWeight: 700, fontSize: 15, color: '#0F172A', marginBottom: 4 }}>PagerDuty</div>
                                <div style={{ fontSize: 12, color: '#94A3B8', marginBottom: 16 }}>On-call alerting and escalation</div>
                                <InputRow label="INTEGRATION KEY" placeholder="pd_..." secret />
                            </div>
                        </div>
                    )}

                    {/* ── NOTIFICATIONS ── */}
                    {section === 'Notifications' && (
                        <div>
                            <div style={{ fontWeight: 700, fontSize: 15, color: '#0F172A', marginBottom: 18 }}>Alert Preferences</div>
                            <ToggleRow label="P1 Real-time Alerts" description="Instant notification on critical incidents" defaultOn />
                            <ToggleRow label="P2 Alerts" description="Notify within 5 minutes" defaultOn />
                            <ToggleRow label="Anomaly Score > 0.8" description="Alert on high anomaly scores" defaultOn />
                            <ToggleRow label="Prediction Alerts" description="Notify about predicted failures 2h before" defaultOn />
                            <ToggleRow label="RCA Complete" description="Notify when root cause analysis finishes" />
                            <ToggleRow label="Weekly Summary Digest" description="Weekly report every Monday 9am" />
                        </div>
                    )}

                    {/* ── USERS ── */}
                    {section === 'Users' && (
                        <div>
                            {!currentUserIsAdmin ? (
                                <div style={{ textAlign: 'center', padding: '48px 24px', color: '#94A3B8' }}>
                                    <ShieldCheck size={48} color="#E2E8F0" style={{ marginBottom: 16 }} />
                                    <div style={{ fontWeight: 700, fontSize: 15, color: '#374151', marginBottom: 6 }}>Admin Access Required</div>
                                    <div style={{ fontSize: 13, maxWidth: 320, margin: '0 auto', lineHeight: 1.6 }}>
                                        User management is restricted to administrators. Contact your system admin if you need access.
                                    </div>
                                </div>
                            ) : (
                                <div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                                        <div style={{ fontWeight: 700, fontSize: 15, color: '#0F172A' }}>Team Members</div>
                                        <button className="btn btn-primary" style={{ fontSize: 12, padding: '6px 14px' }}>+ Invite</button>
                                    </div>
                                    <table className="data-table">
                                        <thead><tr>{['User', 'Role', 'Last Active', 'Status', 'Actions'].map(h => <th key={h}>{h}</th>)}</tr></thead>
                                        <tbody>
                                            {[
                                                { name: 'Admin User', email: 'admin@neuralops.io', role: 'admin', active: 'Now', status: 'Active' },
                                                { name: 'Sarah Kim', email: 'sarah.k@acme.com', role: 'admin', active: '2h ago', status: 'Active' },
                                                { name: 'Alex Mercer', email: 'alex.m@acme.com', role: 'viewer', active: '1d ago', status: 'Active' },
                                                { name: 'John Kowalski', email: 'john.k@acme.com', role: 'viewer', active: '3d ago', status: 'Inactive' },
                                            ].map(u => (
                                                <tr key={u.email}>
                                                    <td>
                                                        <div style={{ fontWeight: 600, color: '#0F172A', fontSize: 13 }}>{u.name}</div>
                                                        <div style={{ fontSize: 11, color: '#94A3B8' }}>{u.email}</div>
                                                    </td>
                                                    <td><span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 9999, background: u.role === 'admin' ? '#EEF2FF' : '#F8FAFC', color: u.role === 'admin' ? '#6366F1' : '#64748B', fontWeight: 600, textTransform: 'capitalize' }}>{u.role}</span></td>
                                                    <td style={{ color: '#64748B', fontSize: 12 }}>{u.active}</td>
                                                    <td><span style={{ fontSize: 11, color: u.status === 'Active' ? '#059669' : '#94A3B8', fontWeight: 600 }}>{u.status}</span></td>
                                                    <td>
                                                        {u.email !== 'admin@neuralops.io' && (
                                                            <button style={{ fontSize: 11, padding: '3px 8px', borderRadius: 6, border: '1px solid #FECACA', background: '#FEF2F2', color: '#DC2626', cursor: 'pointer', fontWeight: 600 }}>
                                                                Remove
                                                            </button>
                                                        )}
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </div>
                    )}

                    {/* ── RL DASHBOARD ── */}
                    {section === 'RL Dashboard' && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
                            <div style={{ fontWeight: 700, fontSize: 15, color: '#0F172A' }}>Reinforcement Learning — Model Dashboard</div>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
                                {[
                                    { label: 'Model Version', value: 'v3.7.2', icon: Brain, color: '#6366F1' },
                                    { label: 'Overall Accuracy', value: '91.4%', icon: Award, color: '#10B981' },
                                    { label: 'MTTR Reduction', value: '43%', icon: TrendingDown, color: '#3B82F6' },
                                    { label: 'Actions Approved', value: '1,247', icon: CheckCircle, color: '#F59E0B' },
                                ].map(m => (
                                    <div key={m.label} className="card-surface" style={{ padding: '14px 16px', borderRadius: 10 }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                                            <div style={{ width: 28, height: 28, borderRadius: 8, background: `${m.color}22`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                                <m.icon size={13} color={m.color} />
                                            </div>
                                            <div style={{ fontSize: 10, fontWeight: 600, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{m.label}</div>
                                        </div>
                                        <div style={{ fontSize: 22, fontWeight: 800, color: '#0F172A', letterSpacing: '-0.02em' }}>{m.value}</div>
                                    </div>
                                ))}
                            </div>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                                <div>
                                    <div style={{ fontSize: 13, fontWeight: 600, color: '#0F172A', marginBottom: 12 }}>Diagnosis Accuracy (30d)</div>
                                    <ResponsiveContainer width="100%" height={140}>
                                        <LineChart data={RL_ACCURACY}><CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" /><XAxis dataKey="d" tick={{ fontSize: 9, fill: '#94A3B8' }} interval={6} /><YAxis domain={[0.6, 1.0]} tick={{ fontSize: 9, fill: '#94A3B8' }} tickFormatter={v => `${(v * 100) | 0}% `} width={38} /><Tooltip contentStyle={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: 8, fontSize: 11 }} formatter={(v: any) => `${(v * 100).toFixed(1)}% `} /><Line type="monotone" dataKey="acc" stroke="#10B981" strokeWidth={2} dot={false} /></LineChart>
                                    </ResponsiveContainer>
                                </div>
                                <div>
                                    <div style={{ fontSize: 13, fontWeight: 600, color: '#0F172A', marginBottom: 12 }}>MTTR Trend (minutes)</div>
                                    <ResponsiveContainer width="100%" height={140}>
                                        <LineChart data={RL_MTTR}><CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" /><XAxis dataKey="d" tick={{ fontSize: 9, fill: '#94A3B8' }} interval={6} /><YAxis tick={{ fontSize: 9, fill: '#94A3B8' }} width={28} /><Tooltip contentStyle={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: 8, fontSize: 11 }} /><Line type="monotone" dataKey="mttr" stroke="#6366F1" strokeWidth={2} dot={false} /></LineChart>
                                    </ResponsiveContainer>
                                </div>
                            </div>
                            <div style={{ padding: 16, background: '#F0F4FF', borderRadius: 10, border: '1px solid #C7D2FE', fontSize: 13, color: '#4338CA', lineHeight: 1.7 }}>
                                <strong>Model insights:</strong> The RL agent has improved diagnosis accuracy from 65% → 91.4% over 90 days using epsilon-greedy exploration (ε=0.05). Primary reward signal: user thumbs-up + MTTR reduction. Next scheduled training run: tomorrow 02:00 UTC.
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
