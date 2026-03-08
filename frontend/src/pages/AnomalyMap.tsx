// frontend/src/pages/AnomalyMap.tsx
import { useState, useEffect, useRef } from 'react';
import { Activity, TrendingUp, AlertTriangle, RefreshCw } from 'lucide-react';

interface ServiceNode {
    id: string;
    name: string;
    x: number;
    y: number;
    score: number;
    region: string;
    provider: 'aws' | 'gcp' | 'azure';
}

const SERVICES: ServiceNode[] = [
    { id: 's1', name: 'api-gateway', x: 420, y: 180, score: 0.85, region: 'us-east-1', provider: 'aws' },
    { id: 's2', name: 'ml-inference', x: 620, y: 140, score: 0.92, region: 'us-west-2', provider: 'aws' },
    { id: 's3', name: 'data-ingestion', x: 240, y: 220, score: 0.32, region: 'eu-west-1', provider: 'aws' },
    { id: 's4', name: 'auth-service', x: 500, y: 300, score: 0.10, region: 'ap-southeast-1', provider: 'gcp' },
    { id: 's5', name: 'redis-cache', x: 340, y: 310, score: 0.55, region: 'us-central1', provider: 'gcp' },
    { id: 's6', name: 'postgres-primary', x: 660, y: 280, score: 0.72, region: 'eastus', provider: 'azure' },
    { id: 's7', name: 'celery-worker', x: 180, y: 360, score: 0.18, region: 'eu-west-1', provider: 'aws' },
    { id: 's8', name: 'notification-svc', x: 750, y: 200, score: 0.42, region: 'ap-southeast-1', provider: 'gcp' },
    { id: 's9', name: 'cdn-origin', x: 120, y: 160, score: 0.05, region: 'global', provider: 'aws' },
];

const EDGES = [
    ['s1', 's2'], ['s1', 's3'], ['s1', 's4'], ['s1', 's5'],
    ['s2', 's6'], ['s3', 's7'], ['s4', 's5'], ['s5', 's6'], ['s8', 's1'], ['s9', 's1'],
];

function scoreColor(s: number) {
    if (s > 0.8) return '#EF4444';
    if (s > 0.6) return '#F97316';
    if (s > 0.4) return '#F59E0B';
    if (s > 0.2) return '#10B981';
    return '#94A3B8';
}

function scoreLabel(s: number) {
    if (s > 0.8) return 'Critical';
    if (s > 0.6) return 'High';
    if (s > 0.4) return 'Medium';
    if (s > 0.2) return 'Low';
    return 'Healthy';
}

export default function AnomalyMap() {
    const [services, setServices] = useState<ServiceNode[]>(SERVICES);
    const [selected, setSelected] = useState<ServiceNode | null>(null);
    const [tick, setTick] = useState(0);

    // Animate scores slightly
    useEffect(() => {
        const t = setInterval(() => {
            setServices(prev => prev.map(s => ({
                ...s,
                score: Math.max(0, Math.min(1, s.score + (Math.random() - 0.5) * 0.04)),
            })));
            setTick(c => c + 1);
        }, 3000);
        return () => clearInterval(t);
    }, []);

    const topAnomalies = [...services].sort((a, b) => b.score - a.score).slice(0, 5);

    return (
        <div className="animate-fade" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                    <h1 style={{ fontSize: 22, fontWeight: 800, color: '#0F172A', letterSpacing: '-0.02em' }}>Anomaly Map</h1>
                    <div style={{ fontSize: 13, color: '#64748B', marginTop: 3 }}>
                        Service dependency graph · Real-time anomaly scores
                    </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
                    <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#10B981' }} />
                    <span style={{ color: '#94A3B8' }}>Live · {new Date().toLocaleTimeString()}</span>
                </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: 16 }}>
                {/* Main graph canvas */}
                <div className="card" style={{ overflow: 'hidden', position: 'relative' }}>
                    <div style={{ padding: '12px 16px', borderBottom: '1px solid #E2E8F0', fontSize: 12, color: '#94A3B8', display: 'flex', alignItems: 'center', gap: 16 }}>
                        <span>Service Dependency Graph</span>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginLeft: 'auto' }}>
                            {[['Critical', '#EF4444'], ['High', '#F97316'], ['Medium', '#F59E0B'], ['Healthy', '#94A3B8']].map(([l, c]) => (
                                <div key={l} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                                    <div style={{ width: 8, height: 8, borderRadius: '50%', background: c }} />
                                    <span style={{ color: '#64748B', fontSize: 11 }}>{l}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                    <svg width="100%" viewBox="0 0 900 460" style={{ display: 'block', background: '#FAFBFF' }}>
                        {/* SVG grid */}
                        <defs>
                            <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
                                <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#EEF2FF" strokeWidth="0.5" />
                            </pattern>
                        </defs>
                        <rect width="900" height="460" fill="url(#grid)" />

                        {/* Edges */}
                        {EDGES.map(([a, b]) => {
                            const na = services.find(s => s.id === a);
                            const nb = services.find(s => s.id === b);
                            if (!na || !nb) return null;
                            return (
                                <line key={`${a}-${b}`}
                                    x1={na.x} y1={na.y} x2={nb.x} y2={nb.y}
                                    stroke="#E2E8F0" strokeWidth={1.5}
                                    strokeDasharray={na.score > 0.7 || nb.score > 0.7 ? '6,4' : '0'}
                                />
                            );
                        })}

                        {/* Nodes */}
                        {services.map(svc => {
                            const color = scoreColor(svc.score);
                            const isSelected = selected?.id === svc.id;
                            const r = 22;
                            return (
                                <g key={svc.id} style={{ cursor: 'pointer' }} onClick={() => setSelected(s => s?.id === svc.id ? null : svc)}>
                                    {/* Pulse ring for high anomalies */}
                                    {svc.score > 0.6 && (
                                        <circle cx={svc.x} cy={svc.y} r={r + 10} fill="none" stroke={color} strokeWidth={1.5} opacity={0.25} />
                                    )}
                                    {/* Selection ring */}
                                    {isSelected && (
                                        <circle cx={svc.x} cy={svc.y} r={r + 6} fill="none" stroke="#6366F1" strokeWidth={2} />
                                    )}
                                    {/* Main circle */}
                                    <circle cx={svc.x} cy={svc.y} r={r} fill="#FFFFFF" stroke={color} strokeWidth={isSelected ? 3 : 2} />
                                    {/* Score text */}
                                    <text x={svc.x} y={svc.y + 4} textAnchor="middle" fontSize="11" fontWeight="700" fill={color} fontFamily="JetBrains Mono, monospace">
                                        {(svc.score * 100).toFixed(0)}
                                    </text>
                                    {/* Service label */}
                                    <text x={svc.x} y={svc.y + r + 14} textAnchor="middle" fontSize="10" fill="#64748B" fontFamily="Inter, sans-serif">
                                        {svc.name.length > 12 ? svc.name.slice(0, 11) + '…' : svc.name}
                                    </text>
                                </g>
                            );
                        })}
                    </svg>

                    {/* Selected service detail */}
                    {selected && (
                        <div style={{
                            position: 'absolute', bottom: 16, left: 16,
                            background: '#FFFFFF', border: '1px solid #E2E8F0',
                            borderRadius: 12, padding: '14px 18px', minWidth: 220,
                            boxShadow: '0 4px 16px rgba(0,0,0,0.08)',
                        }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                                <div style={{ fontWeight: 700, fontSize: 13, color: '#0F172A' }}>{selected.name}</div>
                                <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 9999, background: `${scoreColor(selected.score)}15`, color: scoreColor(selected.score), fontWeight: 600 }}>{scoreLabel(selected.score)}</span>
                            </div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                                <div style={{ fontSize: 12, color: '#64748B' }}>Anomaly Score: <strong style={{ color: scoreColor(selected.score), fontFamily: 'monospace' }}>{selected.score.toFixed(3)}</strong></div>
                                <div style={{ fontSize: 12, color: '#64748B' }}>Region: {selected.region}</div>
                                <div style={{ fontSize: 12, color: '#64748B' }}>Cloud: {selected.provider.toUpperCase()}</div>
                            </div>
                        </div>
                    )}
                </div>

                {/* Right panel */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    {/* Summary */}
                    <div className="card" style={{ padding: '16px 20px' }}>
                        <div style={{ fontSize: 13, fontWeight: 700, color: '#0F172A', marginBottom: 14 }}>System Health</div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                            {[
                                { label: 'Critical', count: services.filter(s => s.score > 0.8).length, color: '#EF4444' },
                                { label: 'High', count: services.filter(s => s.score > 0.6 && s.score <= 0.8).length, color: '#F97316' },
                                { label: 'Medium', count: services.filter(s => s.score > 0.4 && s.score <= 0.6).length, color: '#F59E0B' },
                                { label: 'Healthy', count: services.filter(s => s.score <= 0.4).length, color: '#10B981' },
                            ].map(s => (
                                <div key={s.label} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                    <div style={{ width: 8, height: 8, borderRadius: '50%', background: s.color, flexShrink: 0 }} />
                                    <span style={{ fontSize: 12, color: '#64748B', flex: 1 }}>{s.label}</span>
                                    <span style={{ fontSize: 14, fontWeight: 700, color: '#0F172A', fontFamily: 'monospace' }}>{s.count}</span>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Top anomalies */}
                    <div className="card" style={{ padding: '16px 20px' }}>
                        <div style={{ fontSize: 13, fontWeight: 700, color: '#0F172A', marginBottom: 14 }}>Top Anomalies</div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                            {topAnomalies.map(svc => (
                                <div key={svc.id} style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}
                                    onClick={() => setSelected(svc)}>
                                    <div style={{ width: 32, height: 32, borderRadius: 8, background: `${scoreColor(svc.score)}14`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                                        <Activity size={13} color={scoreColor(svc.score)} />
                                    </div>
                                    <div style={{ flex: 1, overflow: 'hidden' }}>
                                        <div style={{ fontSize: 12, fontWeight: 600, color: '#0F172A', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{svc.name}</div>
                                        <div style={{ fontSize: 10, color: '#94A3B8' }}>{svc.region}</div>
                                    </div>
                                    <span style={{ fontSize: 12, fontWeight: 700, color: scoreColor(svc.score), fontFamily: 'monospace' }}>{(svc.score * 100).toFixed(1)}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
