// frontend/src/pages/Repositories.tsx
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { GitBranch, Plus, ExternalLink, RefreshCw, AlertCircle, CheckCircle, Clock, Trash2, X, GitFork, Star, Loader2 } from 'lucide-react';
import api from '../services/api';

interface Repo {
    repo_id: string;
    name: string;
    owner: string;
    url: string;
    status: string;
    description?: string;
    language?: string;
    stars?: number;
    total_files?: number;
    source_files?: number;
    total_loc?: number;
    total_dependencies?: number;
    issues_found?: number;
    analyzed_at?: string;
    last_commit?: string;
    consecutive_failures?: number;
    error?: string;
}

function RiskBar({ count }: { count: number }) {
    const score = Math.min(1.0, count / 20);
    const color = score > 0.5 ? '#EF4444' : score > 0.25 ? '#F59E0B' : '#10B981';
    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 80, height: 5, background: '#F1F5F9', borderRadius: 4, overflow: 'hidden' }}>
                <div style={{ width: `${score * 100}%`, height: '100%', background: color, borderRadius: 4, transition: 'width 0.5s' }} />
            </div>
            <span style={{ fontSize: 11, color, fontWeight: 600, fontFamily: 'monospace' }}>
                {count > 0 ? `${count} issues` : 'Clean'}
            </span>
        </div>
    );
}

function StatusChip({ status }: { status: string }) {
    const map: Record<string, { icon: any; label: string; bg: string; color: string }> = {
        active: { icon: CheckCircle, label: 'Active', bg: '#ECFDF5', color: '#059669' },
        analyzing: { icon: Loader2, label: 'Analyzing…', bg: '#EEF2FF', color: '#6366F1' },
        error: { icon: AlertCircle, label: 'Error', bg: '#FEF2F2', color: '#DC2626' },
        idle: { icon: Clock, label: 'Idle', bg: '#F8FAFC', color: '#64748B' },
    };
    const s = map[status] || map.idle;
    const Icon = s.icon;
    return (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, padding: '3px 10px', borderRadius: 9999, background: s.bg, color: s.color, fontWeight: 600 }}>
            <Icon size={11} style={status === 'analyzing' ? { animation: 'spin 1s linear infinite' } : {}} />
            {s.label}
        </span>
    );
}

export default function Repositories() {
    const navigate = useNavigate();
    const [repos, setRepos] = useState<Repo[]>([]);
    const [loading, setLoading] = useState(true);
    const [showAdd, setShowAdd] = useState(false);
    const [newUrl, setNewUrl] = useState('');
    const [newToken, setNewToken] = useState('');
    const [adding, setAdding] = useState(false);
    const [addError, setAddError] = useState('');
    const [rescanning, setRescanning] = useState<string>('');

    const loadRepos = useCallback(async () => {
        try {
            const data = await api.getRepositories() as any;
            // Backend returns { repositories: [...] }
            const list = Array.isArray(data) ? data : (data.repositories || []);
            setRepos(list);
        } catch {
            // Backend not running — show empty state
            setRepos([]);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadRepos();
        // Poll every 15s to pick up analysis completions
        const timer = setInterval(loadRepos, 15000);
        return () => clearInterval(timer);
    }, [loadRepos]);

    const addRepo = async () => {
        if (!newUrl.trim()) return;
        setAdding(true);
        setAddError('');
        try {
            const result: any = await api.addRepository(newUrl.trim(), newToken || undefined);
            if (result?.status === 'error') {
                setAddError(result.message || 'Failed to add repository');
                return;
            }
            setNewUrl(''); setNewToken(''); setShowAdd(false);
            // Reload immediately to show the "analyzing" state
            await loadRepos();
        } catch (e: any) {
            setAddError(e.message || 'Failed to add repository. Check that GitHub token is set in backend .env');
        } finally {
            setAdding(false);
        }
    };

    const rescan = async (repo: Repo) => {
        setRescanning(repo.repo_id);
        try {
            await api.rescanRepository(repo.repo_id);
            await loadRepos();
        } catch { /* ignore */ } finally {
            setRescanning('');
        }
    };

    if (loading) {
        return (
            <div className="animate-fade" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                <div style={{ fontSize: 22, fontWeight: 800, color: '#0F172A' }}>Repositories</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 16 }}>
                    {[1, 2, 3].map(i => <div key={i} className="skeleton" style={{ height: 200, borderRadius: 14 }} />)}
                </div>
            </div>
        );
    }

    return (
        <div className="animate-fade" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                    <h1 style={{ fontSize: 22, fontWeight: 800, color: '#0F172A', letterSpacing: '-0.02em' }}>Repositories</h1>
                    <div style={{ fontSize: 13, color: '#64748B', marginTop: 3 }}>
                        {repos.length} repositories tracked · {repos.filter(r => r.status === 'active').length} active
                    </div>
                </div>
                <div style={{ display: 'flex', gap: 10 }}>
                    <button className="btn btn-secondary" onClick={loadRepos}>
                        <RefreshCw size={13} /> Refresh
                    </button>
                    <button className="btn btn-primary" onClick={() => setShowAdd(true)}>
                        <Plus size={14} /> Add Repository
                    </button>
                </div>
            </div>

            {/* Add repo modal */}
            {showAdd && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.15)', zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <div className="card" style={{ width: 480, padding: 28 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                            <div style={{ fontWeight: 700, fontSize: 16, color: '#0F172A' }}>Add Repository</div>
                            <button className="btn btn-ghost" onClick={() => setShowAdd(false)} style={{ padding: 4 }}><X size={16} color="#64748B" /></button>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                            <div>
                                <label style={{ fontSize: 12, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 6 }}>REPOSITORY URL</label>
                                <input className="form-input" value={newUrl} onChange={e => setNewUrl(e.target.value)}
                                    placeholder="https://github.com/owner/repo" onKeyDown={e => e.key === 'Enter' && addRepo()} />
                            </div>
                            <div>
                                <label style={{ fontSize: 12, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 6 }}>
                                    GITHUB TOKEN (optional if set in backend .env)
                                </label>
                                <input className="form-input" type="password" value={newToken} onChange={e => setNewToken(e.target.value)}
                                    placeholder="ghp_xxxxxxxxxxxx" />
                            </div>
                            {addError && (
                                <div style={{ background: '#FEF2F2', border: '1px solid #FCA5A5', borderRadius: 8, padding: '10px 14px', fontSize: 12, color: '#DC2626' }}>
                                    {addError}
                                </div>
                            )}
                            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 8 }}>
                                <button className="btn btn-secondary" onClick={() => { setShowAdd(false); setAddError(''); }}>Cancel</button>
                                <button className="btn btn-primary" onClick={addRepo} disabled={!newUrl.trim() || adding}>
                                    {adding ? <><Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} /> Adding…</> : <><Plus size={13} /> Add & Analyze</>}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Empty state */}
            {repos.length === 0 && (
                <div className="card" style={{ padding: 48, textAlign: 'center' }}>
                    <div style={{ width: 56, height: 56, borderRadius: 16, background: '#EEF2FF', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
                        <GitBranch size={24} color="#6366F1" />
                    </div>
                    <div style={{ fontSize: 16, fontWeight: 700, color: '#0F172A', marginBottom: 8 }}>No repositories tracked yet</div>
                    <div style={{ fontSize: 13, color: '#64748B', maxWidth: 360, margin: '0 auto 20px' }}>
                        Add a GitHub repository to get real code analysis — LOC counts, dependency graph, Phi-3 issue detection, and Gemini code review.
                    </div>
                    <button className="btn btn-primary" onClick={() => setShowAdd(true)}>
                        <Plus size={14} /> Add Repository
                    </button>
                </div>
            )}

            {/* Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 16 }}>
                {repos.map(repo => (
                    <div key={repo.repo_id} className="card" style={{ padding: 20, cursor: 'pointer', transition: 'box-shadow 0.15s, transform 0.15s' }}
                        onClick={() => navigate(`/developer?repo=${encodeURIComponent(repo.repo_id)}`)}
                        onMouseEnter={e => { (e.currentTarget as HTMLElement).style.boxShadow = '0 4px 20px rgba(99,102,241,0.12)'; (e.currentTarget as HTMLElement).style.transform = 'translateY(-1px)'; }}
                        onMouseLeave={e => { (e.currentTarget as HTMLElement).style.boxShadow = ''; (e.currentTarget as HTMLElement).style.transform = ''; }}
                    >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                <div style={{ width: 36, height: 36, borderRadius: 10, background: '#EEF2FF', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                    <GitBranch size={17} color="#6366F1" />
                                </div>
                                <div>
                                    <div style={{ fontWeight: 700, fontSize: 14, color: '#0F172A' }}>{repo.name}</div>
                                    <div style={{ fontSize: 11, color: '#94A3B8' }}>{repo.owner} · {repo.language || 'Unknown'}</div>
                                </div>
                            </div>
                            <StatusChip status={repo.status} />
                        </div>

                        {/* Description */}
                        {repo.description && (
                            <div style={{
                                fontSize: 12, color: '#64748B', marginBottom: 12, lineHeight: 1.5,
                                overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical'
                            }}>
                                {repo.description}
                            </div>
                        )}

                        {/* Stats */}
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginBottom: 14 }}>
                            {[
                                { label: 'Files', value: repo.status === 'analyzing' ? '…' : (repo.total_files ?? '—') },
                                {
                                    label: 'Issues', value: repo.status === 'analyzing' ? '…' : (repo.issues_found ?? '—'),
                                    color: (repo.issues_found || 0) > 10 ? '#EF4444' : (repo.issues_found || 0) > 0 ? '#F59E0B' : '#059669'
                                },
                                { label: 'Deps', value: repo.status === 'analyzing' ? '…' : (repo.total_dependencies ?? '—') },
                            ].map(s => (
                                <div key={s.label} style={{ background: '#F8FAFC', borderRadius: 8, padding: '8px 10px' }}>
                                    <div style={{ fontSize: 10, color: '#94A3B8', fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>{s.label}</div>
                                    <div style={{ fontSize: 15, fontWeight: 700, color: (s as any).color || '#0F172A', marginTop: 2 }}>{s.value}</div>
                                </div>
                            ))}
                        </div>

                        {/* Risk bar */}
                        {repo.status === 'active' && (
                            <div style={{ marginBottom: 12 }}>
                                <div style={{ fontSize: 11, color: '#94A3B8', marginBottom: 5 }}>Issue Severity</div>
                                <RiskBar count={repo.issues_found || 0} />
                            </div>
                        )}

                        {/* Stars + LOC */}
                        {repo.status === 'active' && (
                            <div style={{ display: 'flex', gap: 12, marginBottom: 12, fontSize: 11, color: '#64748B' }}>
                                {repo.stars !== undefined && (
                                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                                        <Star size={11} fill="#F59E0B" color="#F59E0B" /> {repo.stars}
                                    </span>
                                )}
                                {repo.total_loc !== undefined && (
                                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                                        <GitFork size={11} /> {repo.total_loc.toLocaleString()} LOC
                                    </span>
                                )}
                            </div>
                        )}

                        {/* Footer */}
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: 10, borderTop: '1px solid #F1F5F9' }}>
                            <div style={{ fontSize: 11, color: '#94A3B8' }}>
                                {repo.analyzed_at ? `Analyzed ${new Date(repo.analyzed_at).toLocaleDateString()}` :
                                    repo.status === 'analyzing' ? 'Analysis in progress…' : 'Not analyzed yet'}
                            </div>
                            <div style={{ display: 'flex', gap: 6 }}>
                                <button className="btn btn-ghost" style={{ padding: '4px 8px', fontSize: 11 }}
                                    onClick={e => { e.stopPropagation(); rescan(repo); }}
                                    disabled={rescanning === repo.repo_id || repo.status === 'analyzing'}>
                                    <RefreshCw size={11} style={rescanning === repo.repo_id ? { animation: 'spin 1s linear infinite' } : {}} />
                                </button>
                                <button className="btn btn-ghost" style={{ padding: '4px 6px' }}
                                    onClick={e => { e.stopPropagation(); window.open(repo.url, '_blank'); }}>
                                    <ExternalLink size={12} color="#94A3B8" />
                                </button>
                            </div>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
