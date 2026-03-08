// frontend/src/pages/IncidentDetail.tsx
import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ChevronLeft, AlertTriangle, Clock, Activity, CheckCircle, MessageSquare, Shield, Copy, ExternalLink } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import api from '../services/api';

const STATUS_STYLE: Record<string, { bg: string; color: string }> = {
    detected: { bg: '#FEF2F2', color: '#DC2626' },
    investigating: { bg: '#FFFBEB', color: '#D97706' },
    remediating: { bg: '#FFF7ED', color: '#EA580C' },
    resolved: { bg: '#ECFDF5', color: '#059669' },
    false_positive: { bg: '#F8FAFC', color: '#64748B' },
    post_mortem: { bg: '#EEF2FF', color: '#4F46E5' },
};

const RISK_LABELS: Record<string, { bg: string; color: string }> = {
    high: { bg: '#FEF2F2', color: '#DC2626' },
    medium: { bg: '#FFFBEB', color: '#D97706' },
    low: { bg: '#ECFDF5', color: '#059669' },
};

export default function IncidentDetail() {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const [incident, setIncident] = useState<any>(null);
    const [rca, setRca] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState<'overview' | 'rca' | 'actions'>('overview');
    const [copied, setCopied] = useState(false);

    useEffect(() => {
        if (!id) return;
        async function load() {
            try {
                const [incData, rcaData] = await Promise.allSettled([
                    api.getIncident(id!), api.getRCA(id!),
                ]);
                if (incData.status === 'fulfilled') setIncident(incData.value);
                if (rcaData.status === 'fulfilled') setRca(rcaData.value);
            } finally { setLoading(false); }
        }
        load();
    }, [id]);

    const copyId = () => {
        navigator.clipboard.writeText(id || '');
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
    };

    if (loading) return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {[1, 2, 3].map(i => <div key={i} className="skeleton" style={{ height: 80, borderRadius: 14 }} />)}
        </div>
    );

    if (!incident) return (
        <div className="card" style={{ padding: 40 }}>
            <div className="empty-state">
                <div className="empty-state-icon"><AlertTriangle size={22} color="#94A3B8" /></div>
                <div style={{ fontSize: 14, color: '#64748B' }}>Incident not found</div>
                <button className="btn btn-secondary" style={{ marginTop: 16, fontSize: 12 }} onClick={() => navigate('/incidents')}>← Back to Incidents</button>
            </div>
        </div>
    );

    const statusStyle = STATUS_STYLE[incident.status] || { bg: '#F8FAFC', color: '#64748B' };

    const TABS = [
        { id: 'overview', label: 'Overview' },
        { id: 'rca', label: 'Root Cause Analysis' },
        { id: 'actions', label: 'Actions' },
    ];

    return (
        <div className="animate-fade" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* Breadcrumb */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <button className="btn btn-ghost" style={{ padding: '6px 10px', fontSize: 13 }} onClick={() => navigate('/incidents')}>
                    <ChevronLeft size={14} /> Incidents
                </button>
                <span style={{ color: '#E2E8F0' }}>/</span>
                <span style={{ fontSize: 13, color: '#64748B', fontFamily: 'monospace' }}>{id?.slice(0, 8)}…</span>
                <button className="btn btn-ghost" style={{ padding: '4px 6px' }} onClick={copyId} title="Copy incident ID">
                    {copied ? <CheckCircle size={12} color="#10B981" /> : <Copy size={12} color="#94A3B8" />}
                </button>
            </div>

            {/* Header card */}
            <div className="card" style={{ padding: '20px 24px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16 }}>
                    <div style={{ flex: 1 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                            <span className={`badge badge-${incident.severity?.toLowerCase()}`}>{incident.severity}</span>
                            <span style={{ fontSize: 12, padding: '3px 10px', borderRadius: 9999, background: statusStyle.bg, color: statusStyle.color, fontWeight: 600 }}>
                                {incident.status?.replace('_', ' ')}
                            </span>
                            {incident.environment && (
                                <span style={{ fontSize: 12, color: '#94A3B8' }}>{incident.environment} · {incident.cloud_provider}</span>
                            )}
                        </div>
                        <h1 style={{ fontSize: 20, fontWeight: 800, color: '#0F172A', letterSpacing: '-0.02em', lineHeight: 1.3 }}>{incident.title}</h1>
                        {incident.description && (
                            <div style={{ fontSize: 13, color: '#64748B', marginTop: 8, lineHeight: 1.7 }}>{incident.description}</div>
                        )}
                    </div>
                </div>

                {/* Metrics row */}
                <div style={{ display: 'flex', gap: 0, marginTop: 20, borderTop: '1px solid #F1F5F9', paddingTop: 16 }}>
                    {[
                        { label: 'Primary Service', value: incident.primary_service, icon: Activity },
                        { label: 'Detected', value: new Date(incident.detected_at).toLocaleString(), icon: Clock },
                        { label: 'ML Confidence', value: `${((incident.ml_confidence || 0) * 100).toFixed(0)}%`, icon: Shield },
                        { label: 'MTTR', value: incident.mttr_minutes ? `${incident.mttr_minutes}m` : 'Ongoing', icon: Clock },
                    ].map((m, i) => (
                        <div key={m.label} style={{ flex: 1, padding: '0 20px', borderRight: i < 3 ? '1px solid #F1F5F9' : 'none' }}>
                            <div style={{ fontSize: 10, fontWeight: 600, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 4 }}>{m.label}</div>
                            <div style={{ fontSize: 15, fontWeight: 700, color: '#0F172A' }}>{m.value}</div>
                        </div>
                    ))}
                </div>
            </div>

            {/* Tabs */}
            <div style={{ borderBottom: '1px solid #E2E8F0', display: 'flex' }}>
                {TABS.map(t => (
                    <button key={t.id} onClick={() => setActiveTab(t.id as any)} style={{
                        padding: '10px 20px', fontSize: 13, fontWeight: 500, border: 'none',
                        background: 'none', cursor: 'pointer', transition: 'all 0.15s',
                        color: activeTab === t.id ? '#6366F1' : '#64748B',
                        borderBottom: `2px solid ${activeTab === t.id ? '#6366F1' : 'transparent'}`,
                        marginBottom: -1,
                    }}>{t.label}</button>
                ))}
            </div>

            {/* Overview tab */}
            {activeTab === 'overview' && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                    {/* Affected services */}
                    <div className="card" style={{ padding: 20 }}>
                        <div style={{ fontSize: 14, fontWeight: 700, color: '#0F172A', marginBottom: 14 }}>Affected Services</div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                            {(incident.affected_services || [incident.primary_service]).map((svc: string) => (
                                <div key={svc} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', background: '#F8FAFC', borderRadius: 8 }}>
                                    <div style={{ width: 8, height: 8, borderRadius: '50%', background: svc === incident.primary_service ? '#EF4444' : '#F59E0B' }} />
                                    <span style={{ fontSize: 13, color: '#334155', fontWeight: svc === incident.primary_service ? 600 : 400 }}>{svc}</span>
                                    {svc === incident.primary_service && <span style={{ fontSize: 10, color: '#DC2626', marginLeft: 'auto' }}>PRIMARY</span>}
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Blast radius */}
                    <div className="card" style={{ padding: 20 }}>
                        <div style={{ fontSize: 14, fontWeight: 700, color: '#0F172A', marginBottom: 14 }}>Blast Radius</div>
                        {incident.blast_radius ? (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                                    <span style={{ color: '#64748B' }}>Total impacted services</span>
                                    <strong style={{ color: '#0F172A' }}>{incident.blast_radius.total_services_impacted}</strong>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                                    <span style={{ color: '#64748B' }}>User impact</span>
                                    <strong style={{ color: '#0F172A' }}>{incident.blast_radius.estimated_user_impact_percentage?.toFixed(0) ?? '?'}%</strong>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                                    <span style={{ color: '#64748B' }}>SLO breached</span>
                                    <span style={{ color: incident.blast_radius.slo_breached ? '#EF4444' : '#059669', fontWeight: 600 }}>
                                        {incident.blast_radius.slo_breached ? 'Yes' : 'No'}
                                    </span>
                                </div>
                            </div>
                        ) : <div style={{ fontSize: 13, color: '#94A3B8' }}>Calculating blast radius…</div>}
                    </div>

                    {/* Labels */}
                    {incident.labels && Object.keys(incident.labels).length > 0 && (
                        <div className="card" style={{ padding: 20, gridColumn: '1/-1' }}>
                            <div style={{ fontSize: 14, fontWeight: 700, color: '#0F172A', marginBottom: 12 }}>Labels</div>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                                {Object.entries(incident.labels).map(([k, v]) => (
                                    <span key={k} style={{ fontSize: 11, padding: '3px 10px', borderRadius: 9999, background: '#E0E7FF', color: '#4338CA', fontFamily: 'monospace' }}>
                                        {k}={String(v)}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* RCA tab */}
            {activeTab === 'rca' && (
                !rca ? (
                    <div className="card">
                        <div className="empty-state">
                            <div className="empty-state-icon"><Activity size={22} color="#94A3B8" /></div>
                            <div style={{ fontSize: 14, color: '#64748B' }}>RCA not generated yet</div>
                            <div style={{ fontSize: 12, color: '#94A3B8', marginTop: 4 }}>Analysis will appear here once complete</div>
                        </div>
                    </div>
                ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                        {/* Summary */}
                        <div className="card" style={{ padding: 20, borderLeft: '3px solid #6366F1' }}>
                            <div style={{ fontSize: 14, fontWeight: 700, color: '#0F172A', marginBottom: 10 }}>Root Cause Summary</div>
                            <div style={{ fontSize: 13, color: '#334155', lineHeight: 1.8 }}>{rca.root_cause_summary}</div>
                            <div style={{ display: 'flex', gap: 10, marginTop: 12, flexWrap: 'wrap' }}>
                                <span style={{ fontSize: 11, padding: '3px 10px', borderRadius: 9999, background: '#EEF2FF', color: '#6366F1', fontWeight: 600 }}>
                                    {(rca.root_cause_confidence * 100).toFixed(0)}% confidence
                                </span>
                                <span style={{ fontSize: 11, padding: '3px 10px', borderRadius: 9999, ...RISK_LABELS[rca.recurrence_risk || 'low'], fontWeight: 600 }}>
                                    {rca.recurrence_risk?.toUpperCase()} recurrence risk
                                </span>
                                <span style={{ fontSize: 11, padding: '3px 10px', borderRadius: 9999, background: '#F8FAFC', color: '#64748B', border: '1px solid #E2E8F0' }}>
                                    via {rca.llm_provider_used}
                                </span>
                            </div>
                        </div>

                        {/* Contributing factors */}
                        <div className="card" style={{ padding: 20 }}>
                            <div style={{ fontSize: 14, fontWeight: 700, color: '#0F172A', marginBottom: 12 }}>Contributing Factors</div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                <div style={{ padding: '10px 14px', background: '#FEF2F2', borderRadius: 8, border: '1px solid #FECACA', fontSize: 13, color: '#DC2626', fontWeight: 600 }}>
                                    📌 {rca.primary_contributing_factor}
                                </div>
                                {rca.secondary_contributing_factors?.map((f: string, i: number) => (
                                    <div key={i} style={{ padding: '10px 14px', background: '#F8FAFC', borderRadius: 8, fontSize: 13, color: '#334155' }}>
                                        {i + 1}. {f}
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Remediation steps */}
                        {rca.remediation_steps?.length > 0 && (
                            <div className="card" style={{ padding: 20 }}>
                                <div style={{ fontSize: 14, fontWeight: 700, color: '#0F172A', marginBottom: 14 }}>Remediation Playbook</div>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                                    {rca.remediation_steps.map((step: any) => {
                                        const riskStyle = RISK_LABELS[step.risk_level] || RISK_LABELS.low;
                                        return (
                                            <div key={step.step_number} style={{ display: 'flex', gap: 14, padding: '14px 16px', background: '#F8FAFC', borderRadius: 10, border: '1px solid #E2E8F0' }}>
                                                <div style={{ width: 26, height: 26, borderRadius: '50%', background: '#E0E7FF', color: '#4338CA', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 700, flexShrink: 0 }}>
                                                    {step.step_number}
                                                </div>
                                                <div style={{ flex: 1 }}>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                                                        <div style={{ fontSize: 13, fontWeight: 600, color: '#0F172A' }}>{step.action}</div>
                                                        <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                                                            <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 9999, ...riskStyle, fontWeight: 600, textTransform: 'capitalize' }}>{step.risk_level} risk</span>
                                                            {step.automation_eligible && (
                                                                <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 9999, background: '#ECFDF5', color: '#059669', fontWeight: 600 }}>Auto-eligible</span>
                                                            )}
                                                        </div>
                                                    </div>
                                                    <div style={{ fontSize: 12, color: '#64748B', marginTop: 4 }}>{step.rationale}</div>
                                                    {step.estimated_duration_minutes && (
                                                        <div style={{ fontSize: 11, color: '#94A3B8', marginTop: 4 }}>
                                                            ~{step.estimated_duration_minutes}m estimated
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        )}

                        {/* Runbook */}
                        {rca.runbook_markdown && (
                            <div className="card" style={{ padding: 20 }}>
                                <div style={{ fontSize: 14, fontWeight: 700, color: '#0F172A', marginBottom: 14 }}>Auto-generated Runbook</div>
                                <div style={{ fontSize: 13, color: '#334155', lineHeight: 1.8 }}>
                                    <ReactMarkdown>{rca.runbook_markdown}</ReactMarkdown>
                                </div>
                            </div>
                        )}
                    </div>
                )
            )}

            {/* Actions tab */}
            {activeTab === 'actions' && (
                <div className="card">
                    <div className="empty-state">
                        <div className="empty-state-icon"><CheckCircle size={22} color="#94A3B8" /></div>
                        <div style={{ fontSize: 14, color: '#64748B' }}>No pending actions</div>
                        <div style={{ fontSize: 12, color: '#94A3B8', marginTop: 4 }}>Automated remediation actions will appear here once approved</div>
                    </div>
                </div>
            )}
        </div>
    );
}
