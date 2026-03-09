// frontend/src/pages/IncidentHistory.tsx
// Paginated, filterable, sortable incident history table with detail drawer
import { useState, useEffect, useCallback } from 'react';
import {
    History, Search, Filter, ChevronUp, ChevronDown, ChevronLeft, ChevronRight,
    X, Clock, AlertTriangle, CheckCircle, AlertOctagon, Flame, HelpCircle,
    ExternalLink
} from 'lucide-react';
import api from '../services/api';
import { useProject } from '../context/ProjectContext';

interface IncidentRow {
    incident_id: string;
    title: string;
    severity: string;
    status: string;
    detected_at: string | null;
    resolved_at: string | null;
    mttr_minutes: number | null;
    primary_service: string;
    affected_services: string[];
    root_cause: string | null;
    remediation_steps: string[];
    description: string | null;
    environment: string;
    cloud_provider: string;
    peak_anomaly_score: number;
    ml_confidence: number;
    repo_id: string | null;
}

const SEV_COLORS: Record<string, { bg: string; color: string }> = {
    P1: { bg: '#FEF2F2', color: '#DC2626' },
    P2: { bg: '#FFF7ED', color: '#EA580C' },
    P3: { bg: '#FEF9C3', color: '#CA8A04' },
    P4: { bg: '#F0FDF4', color: '#16A34A' },
};

const STATUS_COLORS: Record<string, { bg: string; color: string }> = {
    detected: { bg: '#FFF7ED', color: '#EA580C' },
    investigating: { bg: '#EFF6FF', color: '#2563EB' },
    remediating: { bg: '#F0FDF4', color: '#16A34A' },
    resolved: { bg: '#ECFDF5', color: '#059669' },
    post_mortem: { bg: '#F5F3FF', color: '#7C3AED' },
    false_positive: { bg: '#F8FAFC', color: '#64748B' },
};

function SevBadge({ sev }: { sev: string }) {
    const c = SEV_COLORS[sev] || { bg: '#F1F5F9', color: '#475569' };
    return (
        <span style={{ padding: '2px 8px', borderRadius: 9999, fontWeight: 800, fontSize: 11, background: c.bg, color: c.color }}>
            {sev}
        </span>
    );
}

function StatusBadge({ status }: { status: string }) {
    const c = STATUS_COLORS[status] || { bg: '#F1F5F9', color: '#475569' };
    const label = status.replace(/_/g, ' ');
    return (
        <span style={{ padding: '2px 8px', borderRadius: 9999, fontWeight: 600, fontSize: 10, background: c.bg, color: c.color, textTransform: 'capitalize' }}>
            {label}
        </span>
    );
}

function SortIcon({ col, sortBy, sortOrder }: { col: string; sortBy: string; sortOrder: string }) {
    if (sortBy !== col) return <ChevronUp size={12} color="#D1D5DB" />;
    return sortOrder === 'asc' ? <ChevronUp size={12} color="#6366F1" /> : <ChevronDown size={12} color="#6366F1" />;
}

function formatMttr(minutes: number | null) {
    if (!minutes) return '—';
    if (minutes < 60) return `${Math.round(minutes)}m`;
    const h = Math.floor(minutes / 60);
    const m = Math.round(minutes % 60);
    return `${h}h ${m}m`;
}

function formatDate(d: string | null) {
    if (!d) return '—';
    return new Date(d).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

// ── Detail Drawer ─────────────────────────────────────────────────────────────
function DetailDrawer({ incident, onClose }: { incident: IncidentRow; onClose: () => void }) {
    return (
        <div style={{
            position: 'fixed', top: 0, right: 0, bottom: 0, width: 500, zIndex: 200,
            background: '#fff', borderLeft: '1px solid #E2E8F0',
            boxShadow: '-8px 0 32px rgba(0,0,0,0.08)',
            display: 'flex', flexDirection: 'column',
            animation: 'slide-in-right 0.2s ease',
        }}>
            <div style={{ padding: '16px 20px', borderBottom: '1px solid #E2E8F0', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                        <SevBadge sev={incident.severity} />
                        <StatusBadge status={incident.status} />
                    </div>
                    <div style={{ fontWeight: 700, fontSize: 15, color: '#0F172A', lineHeight: 1.3 }}>{incident.title}</div>
                </div>
                <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}>
                    <X size={18} color="#94A3B8" />
                </button>
            </div>

            <div style={{ flex: 1, overflowY: 'auto', padding: 20, display: 'flex', flexDirection: 'column', gap: 20 }}>
                {/* Timeline */}
                <div>
                    <div style={{ fontWeight: 700, fontSize: 12, color: '#374151', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Timeline</div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 16px' }}>
                        {[
                            ['Detected', incident.detected_at],
                            ['Resolved', incident.resolved_at],
                        ].map(([label, val]) => (
                            <div key={String(label)} style={{ background: '#F8FAFC', borderRadius: 8, padding: '10px 12px' }}>
                                <div style={{ fontSize: 10, color: '#94A3B8', fontWeight: 600, marginBottom: 3 }}>{String(label)}</div>
                                <div style={{ fontSize: 12, color: '#0F172A', fontWeight: 600 }}>{val ? formatDate(String(val)) : '—'}</div>
                            </div>
                        ))}
                        <div style={{ background: '#F8FAFC', borderRadius: 8, padding: '10px 12px' }}>
                            <div style={{ fontSize: 10, color: '#94A3B8', fontWeight: 600, marginBottom: 3 }}>MTTR</div>
                            <div style={{ fontSize: 12, color: '#0F172A', fontWeight: 600 }}>{formatMttr(incident.mttr_minutes)}</div>
                        </div>
                        <div style={{ background: '#F8FAFC', borderRadius: 8, padding: '10px 12px' }}>
                            <div style={{ fontSize: 10, color: '#94A3B8', fontWeight: 600, marginBottom: 3 }}>ML Confidence</div>
                            <div style={{ fontSize: 12, color: '#0F172A', fontWeight: 600 }}>{Math.round(incident.ml_confidence * 100)}%</div>
                        </div>
                    </div>
                </div>

                {/* Services */}
                <div>
                    <div style={{ fontWeight: 700, fontSize: 12, color: '#374151', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Affected Services</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                        {[incident.primary_service, ...incident.affected_services.filter(s => s !== incident.primary_service)].map(s => (
                            <span key={s} style={{ padding: '3px 10px', borderRadius: 8, background: '#EEF2FF', color: '#4F46E5', fontSize: 11, fontWeight: 600 }}>{s}</span>
                        ))}
                    </div>
                </div>

                {/* Description */}
                {incident.description && (
                    <div>
                        <div style={{ fontWeight: 700, fontSize: 12, color: '#374151', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Description</div>
                        <div style={{ fontSize: 13, color: '#64748B', lineHeight: 1.6 }}>{incident.description}</div>
                    </div>
                )}

                {/* Root Cause */}
                <div>
                    <div style={{ fontWeight: 700, fontSize: 12, color: '#374151', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Root Cause</div>
                    <div style={{ background: '#FFFBEB', border: '1px solid #FDE68A', borderRadius: 8, padding: '12px 14px', fontSize: 13, color: '#78350F', lineHeight: 1.6 }}>
                        {incident.root_cause || 'Root cause analysis not yet available.'}
                    </div>
                </div>

                {/* Remediation */}
                {incident.remediation_steps.length > 0 && (
                    <div>
                        <div style={{ fontWeight: 700, fontSize: 12, color: '#374151', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Remediation Steps</div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                            {incident.remediation_steps.map((step, idx) => (
                                <div key={idx} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                                    <div style={{
                                        width: 20, height: 20, borderRadius: '50%', flexShrink: 0,
                                        background: 'linear-gradient(135deg, #6366F1, #3B82F6)',
                                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                                        fontSize: 10, fontWeight: 700, color: '#fff', marginTop: 1,
                                    }}>
                                        {idx + 1}
                                    </div>
                                    <div style={{ fontSize: 13, color: '#374151', lineHeight: 1.5 }}>{step}</div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Environment */}
                <div>
                    <div style={{ fontWeight: 700, fontSize: 12, color: '#374151', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Context</div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 16px' }}>
                        {[
                            ['Environment', incident.environment],
                            ['Cloud Provider', incident.cloud_provider],
                            ['Anomaly Score', (incident.peak_anomaly_score * 100).toFixed(1) + '%'],
                            ['Service', incident.primary_service],
                        ].map(([label, val]) => (
                            <div key={String(label)} style={{ background: '#F8FAFC', borderRadius: 8, padding: '10px 12px' }}>
                                <div style={{ fontSize: 10, color: '#94A3B8', fontWeight: 600, marginBottom: 3 }}>{String(label)}</div>
                                <div style={{ fontSize: 12, color: '#0F172A', fontWeight: 600 }}>{String(val) || '—'}</div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            <style>{`@keyframes slide-in-right { from { transform: translateX(30px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }`}</style>
        </div>
    );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function IncidentHistory() {
    const { selectedProject } = useProject();
    const [incidents, setIncidents] = useState<IncidentRow[]>([]);
    const [totalCount, setTotalCount] = useState(0);
    const [totalPages, setTotalPages] = useState(1);
    const [loading, setLoading] = useState(true);
    const [page, setPage] = useState(1);
    const perPage = 25;

    // Filters
    const [search, setSearch] = useState('');
    const [severity, setSeverity] = useState('');
    const [status, setStatus] = useState('');
    const [fromDate, setFromDate] = useState('');
    const [toDate, setToDate] = useState('');
    const [sortBy, setSortBy] = useState('detected_at');
    const [sortOrder, setSortOrder] = useState('desc');

    // Detail drawer
    const [detail, setDetail] = useState<IncidentRow | null>(null);

    const fetchHistory = useCallback(async () => {
        setLoading(true);
        try {
            const params = new URLSearchParams({
                page: String(page),
                per_page: String(perPage),
                sort_by: sortBy,
                sort_order: sortOrder,
            });
            if (search) params.set('search', search);
            if (severity) params.set('severity', severity);
            if (status) params.set('status', status);
            if (fromDate) params.set('from_date', fromDate);
            if (toDate) params.set('to_date', toDate);
            if (selectedProject) params.set('project_id', selectedProject.id);

            const data = await (api as any).get(`/api/v1/incidents/history?${params.toString()}`) as any;
            setIncidents(data.incidents || []);
            setTotalCount(data.total_count || 0);
            setTotalPages(data.total_pages || 1);
        } catch {
            setIncidents([]);
            setTotalCount(0);
        } finally {
            setLoading(false);
        }
    }, [page, sortBy, sortOrder, search, severity, status, fromDate, toDate, selectedProject]);

    useEffect(() => {
        fetchHistory();
    }, [fetchHistory]);

    const handleSort = (col: string) => {
        if (sortBy === col) setSortOrder(o => o === 'asc' ? 'desc' : 'asc');
        else { setSortBy(col); setSortOrder('desc'); }
        setPage(1);
    };

    const colStyle = (col: string): React.CSSProperties => ({
        padding: '10px 14px', fontWeight: 700, fontSize: 11, color: '#475569',
        cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap',
        textTransform: 'uppercase', letterSpacing: '0.04em', verticalAlign: 'middle',
    });

    const tdStyle: React.CSSProperties = {
        padding: '10px 14px', fontSize: 12, color: '#374151', verticalAlign: 'middle',
        borderBottom: '1px solid #F1F5F9',
    };

    return (
        <div style={{ position: 'relative' }}>
            {/* Page header */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{
                        width: 38, height: 38, borderRadius: 10,
                        background: 'linear-gradient(135deg, #6366F1, #3B82F6)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        boxShadow: '0 4px 12px rgba(99,102,241,0.3)',
                    }}>
                        <History size={18} color="#fff" />
                    </div>
                    <div>
                        <h2 style={{ margin: 0, fontSize: 18, fontWeight: 800, color: '#0F172A' }}>Incident History</h2>
                        <div style={{ fontSize: 12, color: '#64748B', marginTop: 1 }}>
                            {totalCount.toLocaleString()} total incident{totalCount !== 1 ? 's' : ''}
                            {selectedProject ? ` · ${selectedProject.name}` : ''}
                        </div>
                    </div>
                </div>
            </div>

            {/* Filters bar */}
            <div style={{
                display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center',
                background: '#fff', padding: '12px 16px', borderRadius: 12, border: '1px solid #E2E8F0',
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 200, border: '1px solid #E2E8F0', borderRadius: 8, padding: '7px 12px', background: '#F8FAFC' }}>
                    <Search size={14} color="#94A3B8" />
                    <input
                        value={search}
                        onChange={e => { setSearch(e.target.value); setPage(1); }}
                        placeholder="Search title, root cause…"
                        style={{ border: 'none', background: 'transparent', outline: 'none', fontSize: 12, width: '100%' }}
                    />
                </div>

                <select value={severity} onChange={e => { setSeverity(e.target.value); setPage(1); }} style={{ padding: '8px 10px', borderRadius: 8, border: '1px solid #E2E8F0', fontSize: 12, background: '#F8FAFC', color: '#374151', outline: 'none' }}>
                    <option value="">All Severities</option>
                    {['P1', 'P2', 'P3', 'P4'].map(s => <option key={s} value={s}>{s}</option>)}
                </select>

                <select value={status} onChange={e => { setStatus(e.target.value); setPage(1); }} style={{ padding: '8px 10px', borderRadius: 8, border: '1px solid #E2E8F0', fontSize: 12, background: '#F8FAFC', color: '#374151', outline: 'none' }}>
                    <option value="">All Statuses</option>
                    {['detected', 'investigating', 'remediating', 'resolved', 'post_mortem', 'false_positive'].map(s => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
                </select>

                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ fontSize: 11, color: '#94A3B8', fontWeight: 600 }}>FROM</span>
                    <input type="date" value={fromDate} onChange={e => { setFromDate(e.target.value); setPage(1); }} style={{ padding: '7px 10px', borderRadius: 8, border: '1px solid #E2E8F0', fontSize: 12, background: '#F8FAFC', outline: 'none' }} />
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ fontSize: 11, color: '#94A3B8', fontWeight: 600 }}>TO</span>
                    <input type="date" value={toDate} onChange={e => { setToDate(e.target.value); setPage(1); }} style={{ padding: '7px 10px', borderRadius: 8, border: '1px solid #E2E8F0', fontSize: 12, background: '#F8FAFC', outline: 'none' }} />
                </div>

                {(search || severity || status || fromDate || toDate) && (
                    <button onClick={() => { setSearch(''); setSeverity(''); setStatus(''); setFromDate(''); setToDate(''); setPage(1); }} style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '7px 12px', borderRadius: 8, border: '1px solid #E2E8F0', background: '#F8FAFC', cursor: 'pointer', fontSize: 12, color: '#EF4444', fontWeight: 600 }}>
                        <X size={12} /> Clear
                    </button>
                )}
            </div>

            {/* Table */}
            <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #E2E8F0', overflow: 'hidden' }}>
                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ background: '#F8FAFC', borderBottom: '1px solid #E2E8F0' }}>
                                {[
                                    ['title', 'Title'],
                                    ['severity', 'Severity'],
                                    ['status', 'Status'],
                                    ['primary_service', 'Service'],
                                    ['detected_at', 'Started'],
                                    ['resolved_at', 'Resolved'],
                                    ['mttr_minutes', 'MTTR'],
                                ].map(([col, label]) => (
                                    <th key={col} onClick={() => handleSort(col)} style={colStyle(col)}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                                            {label}
                                            <SortIcon col={col} sortBy={sortBy} sortOrder={sortOrder} />
                                        </div>
                                    </th>
                                ))}
                                <th style={{ ...colStyle(''), cursor: 'default' }}>Root Cause</th>
                                <th style={{ ...colStyle(''), cursor: 'default', textAlign: 'center' }}>Detail</th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading ? (
                                <tr><td colSpan={9} style={{ ...tdStyle, textAlign: 'center', padding: 40, color: '#94A3B8' }}>Loading…</td></tr>
                            ) : incidents.length === 0 ? (
                                <tr><td colSpan={9} style={{ ...tdStyle, textAlign: 'center', padding: 48, color: '#94A3B8' }}>
                                    <History size={28} color="#CBD5E1" style={{ display: 'block', margin: '0 auto 8px' }} />
                                    No incidents match your filters
                                </td></tr>
                            ) : incidents.map((inc, idx) => (
                                <tr
                                    key={inc.incident_id}
                                    style={{
                                        background: idx % 2 === 0 ? '#fff' : '#FAFBFF',
                                        cursor: 'pointer', transition: 'background 0.1s',
                                    }}
                                    onMouseEnter={e => (e.currentTarget.style.background = '#F5F3FF')}
                                    onMouseLeave={e => (e.currentTarget.style.background = idx % 2 === 0 ? '#fff' : '#FAFBFF')}
                                    onClick={() => setDetail(inc)}
                                >
                                    <td style={{ ...tdStyle, maxWidth: 300 }}>
                                        <div style={{ fontWeight: 600, color: '#0F172A', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                            {inc.title}
                                        </div>
                                    </td>
                                    <td style={tdStyle}><SevBadge sev={inc.severity} /></td>
                                    <td style={tdStyle}><StatusBadge status={inc.status} /></td>
                                    <td style={tdStyle}>
                                        <span style={{ padding: '2px 8px', borderRadius: 6, background: '#EEF2FF', color: '#4F46E5', fontSize: 11, fontWeight: 600 }}>
                                            {inc.primary_service}
                                        </span>
                                    </td>
                                    <td style={{ ...tdStyle, whiteSpace: 'nowrap' }}>{formatDate(inc.detected_at)}</td>
                                    <td style={{ ...tdStyle, whiteSpace: 'nowrap' }}>{formatDate(inc.resolved_at)}</td>
                                    <td style={{ ...tdStyle, whiteSpace: 'nowrap', fontWeight: 600, color: inc.mttr_minutes && inc.mttr_minutes < 30 ? '#10B981' : inc.mttr_minutes && inc.mttr_minutes > 120 ? '#EF4444' : '#0F172A' }}>
                                        {formatMttr(inc.mttr_minutes)}
                                    </td>
                                    <td style={{ ...tdStyle, maxWidth: 260 }}>
                                        <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: '#64748B', fontSize: 11 }}>
                                            {inc.root_cause || '—'}
                                        </div>
                                    </td>
                                    <td style={{ ...tdStyle, textAlign: 'center' }}>
                                        <button
                                            onClick={e => { e.stopPropagation(); setDetail(inc); }}
                                            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6366F1', padding: 4 }}
                                            title="View details"
                                        >
                                            <ExternalLink size={14} />
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                {/* Pagination */}
                {totalPages > 1 && (
                    <div style={{ padding: '12px 16px', borderTop: '1px solid #F1F5F9', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <div style={{ fontSize: 12, color: '#94A3B8' }}>
                            Showing {((page - 1) * perPage) + 1}–{Math.min(page * perPage, totalCount)} of {totalCount.toLocaleString()}
                        </div>
                        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                            <button
                                onClick={() => setPage(p => Math.max(1, p - 1))}
                                disabled={page === 1}
                                style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #E2E8F0', background: page === 1 ? '#F8FAFC' : '#fff', cursor: page === 1 ? 'not-allowed' : 'pointer', color: page === 1 ? '#CBD5E1' : '#374151' }}
                            >
                                <ChevronLeft size={14} />
                            </button>
                            {Array.from({ length: Math.min(7, totalPages) }, (_, i) => {
                                let p;
                                if (totalPages <= 7) p = i + 1;
                                else if (page <= 4) p = i + 1;
                                else if (page >= totalPages - 3) p = totalPages - 6 + i;
                                else p = page - 3 + i;
                                return (
                                    <button
                                        key={p}
                                        onClick={() => setPage(p)}
                                        style={{
                                            width: 32, height: 32, borderRadius: 6,
                                            border: p === page ? 'none' : '1px solid #E2E8F0',
                                            background: p === page ? 'linear-gradient(135deg, #6366F1, #3B82F6)' : '#fff',
                                            cursor: 'pointer', fontSize: 12, fontWeight: 600,
                                            color: p === page ? '#fff' : '#374151',
                                        }}
                                    >{p}</button>
                                );
                            })}
                            <button
                                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                                disabled={page === totalPages}
                                style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #E2E8F0', background: page === totalPages ? '#F8FAFC' : '#fff', cursor: page === totalPages ? 'not-allowed' : 'pointer', color: page === totalPages ? '#CBD5E1' : '#374151' }}
                            >
                                <ChevronRight size={14} />
                            </button>
                        </div>
                    </div>
                )}
            </div>

            {/* Detail Drawer */}
            {detail && <DetailDrawer incident={detail} onClose={() => setDetail(null)} />}
            {detail && <div style={{ position: 'fixed', inset: 0, zIndex: 199, background: 'rgba(0,0,0,0.1)' }} onClick={() => setDetail(null)} />}
        </div>
    );
}
