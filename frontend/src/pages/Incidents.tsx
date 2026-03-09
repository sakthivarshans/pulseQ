import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Filter, ChevronRight, AlertTriangle, RefreshCw } from 'lucide-react';
import api from '../services/api';
import { useProject } from '../context/ProjectContext';

const STATUS_OPTIONS = ['', 'detected', 'investigating', 'remediating', 'resolved', 'false_positive'];
const SEVERITY_OPTIONS = ['', 'P1', 'P2', 'P3', 'P4'];

const STATUS_STYLE: Record<string, { bg: string; color: string }> = {
    detected: { bg: '#FEF2F2', color: '#DC2626' },
    investigating: { bg: '#FFFBEB', color: '#D97706' },
    remediating: { bg: '#FFF7ED', color: '#EA580C' },
    resolved: { bg: '#ECFDF5', color: '#059669' },
    false_positive: { bg: '#F8FAFC', color: '#64748B' },
    post_mortem: { bg: '#EEF2FF', color: '#4F46E5' },
};

export default function Incidents() {
    const navigate = useNavigate();
    const { selectedProject } = useProject();
    const [incidents, setIncidents] = useState<any[]>([]);
    const [total, setTotal] = useState(0);
    const [status, setStatus] = useState('');
    const [severity, setSeverity] = useState('');
    const [offset, setOffset] = useState(0);
    const limit = 20;
    const [loading, setLoading] = useState(false);

    async function load() {
        setLoading(true);
        try {
            const params: Record<string, any> = {
                status: status || undefined,
                severity: severity || undefined,
                limit,
                offset,
            };
            if (selectedProject) params.project_id = selectedProject.id;
            const data = await api.getIncidents(params);
            setIncidents(data.incidents);
            setTotal(data.total ?? data.incidents.length);
        } catch { setIncidents([]); } finally { setLoading(false); }
    }

    useEffect(() => { load(); }, [status, severity, offset, selectedProject?.id]);

    return (
        <div className="animate-fade" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                    <h1 style={{ fontSize: 22, fontWeight: 800, color: '#0F172A', letterSpacing: '-0.02em' }}>Incidents</h1>
                    <div style={{ fontSize: 13, color: '#64748B', marginTop: 3 }}>
                        {selectedProject ? <span style={{ color: '#6366F1', fontWeight: 600 }}>{selectedProject.owner}/{selectedProject.name} · </span> : null}
                        {total} incidents · {incidents.filter(i => !['resolved', 'false_positive'].includes(i.status)).length} active
                    </div>
                </div>
                <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                    <button className="btn btn-ghost" onClick={load} title="Refresh" style={{ padding: '8px' }}>
                        <RefreshCw size={14} color="#64748B" className={loading ? 'animate-spin' : ''} />
                    </button>
                    <Filter size={14} color="#94A3B8" />
                    <select value={severity} onChange={e => { setSeverity(e.target.value); setOffset(0); }} className="form-select">
                        {SEVERITY_OPTIONS.map(s => <option key={s} value={s}>{s || 'All Severities'}</option>)}
                    </select>
                    <select value={status} onChange={e => { setStatus(e.target.value); setOffset(0); }} className="form-select">
                        {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s ? s.replace('_', ' ') : 'All Statuses'}</option>)}
                    </select>
                </div>
            </div>

            {/* Table */}
            <div className="card" style={{ overflow: 'hidden' }}>
                {loading ? (
                    <div style={{ padding: 24 }}>
                        {[1, 2, 3, 4, 5].map(i => (
                            <div key={i} className="skeleton" style={{ height: 52, borderRadius: 8, marginBottom: 8 }} />
                        ))}
                    </div>
                ) : (
                    <>
                        <table className="data-table">
                            <thead>
                                <tr>
                                    {['Severity', 'Title', 'Services', 'ML Confidence', 'Status', 'Detected', ''].map(h => (
                                        <th key={h}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {incidents.map(inc => {
                                    const s = STATUS_STYLE[inc.status] || { bg: '#F8FAFC', color: '#64748B' };
                                    return (
                                        <tr key={inc.incident_id} onClick={() => navigate(`/incidents/${inc.incident_id}`)}>
                                            <td><span className={`badge badge-${inc.severity?.toLowerCase()}`}>{inc.severity}</span></td>
                                            <td style={{ maxWidth: 320 }}>
                                                <div style={{ fontWeight: 600, color: '#0F172A', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{inc.title}</div>
                                                <div style={{ fontSize: 11, color: '#94A3B8', marginTop: 2 }}>{inc.environment} · {inc.cloud_provider}</div>
                                            </td>
                                            <td>
                                                <div style={{ fontSize: 12, color: '#334155' }}>{inc.primary_service}</div>
                                                {(inc.affected_services?.length || 0) > 1 && (
                                                    <div style={{ fontSize: 10, color: '#94A3B8', marginTop: 1 }}>+{inc.affected_services.length - 1} more</div>
                                                )}
                                            </td>
                                            <td>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                                    <div style={{ width: 60, height: 5, background: '#F1F5F9', borderRadius: 4, overflow: 'hidden' }}>
                                                        <div style={{ width: `${(inc.ml_confidence || 0) * 100}%`, height: '100%', background: '#6366F1', borderRadius: 4 }} />
                                                    </div>
                                                    <span style={{ fontSize: 11, color: '#64748B', fontFamily: 'monospace' }}>
                                                        {((inc.ml_confidence || 0) * 100).toFixed(0)}%
                                                    </span>
                                                </div>
                                            </td>
                                            <td>
                                                <span style={{ fontSize: 11, padding: '3px 10px', borderRadius: 9999, background: s.bg, color: s.color, fontWeight: 600 }}>
                                                    {inc.status?.replace('_', ' ')}
                                                </span>
                                            </td>
                                            <td style={{ color: '#64748B', fontSize: 12 }}>
                                                {new Date(inc.detected_at).toLocaleString()}
                                            </td>
                                            <td><ChevronRight size={14} color="#CBD5E1" /></td>
                                        </tr>
                                    );
                                })}
                                {incidents.length === 0 && (
                                    <tr><td colSpan={7}>
                                        <div className="empty-state">
                                            <div className="empty-state-icon"><AlertTriangle size={22} color="#94A3B8" /></div>
                                            <div style={{ fontSize: 14, color: '#64748B' }}>No incidents found</div>
                                            <div style={{ fontSize: 12, color: '#94A3B8', marginTop: 4 }}>
                                                {status || severity ? 'Try adjusting your filters' : 'All systems are operating normally'}
                                            </div>
                                        </div>
                                    </td></tr>
                                )}
                            </tbody>
                        </table>
                        {/* Pagination */}
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 20px', borderTop: '1px solid #E2E8F0' }}>
                            <span style={{ fontSize: 12, color: '#94A3B8' }}>
                                {total > 0 ? `Showing ${offset + 1}–${Math.min(offset + limit, total)} of ${total}` : '0 results'}
                            </span>
                            <div style={{ display: 'flex', gap: 8 }}>
                                <button className="btn btn-secondary" style={{ fontSize: 12, padding: '5px 12px' }} disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>Previous</button>
                                <button className="btn btn-secondary" style={{ fontSize: 12, padding: '5px 12px' }} disabled={offset + limit >= total} onClick={() => setOffset(offset + limit)}>Next</button>
                            </div>
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}
