// frontend/src/components/ProjectSelector.tsx
import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { GitBranch, ChevronDown, Circle, Plus, Layers } from 'lucide-react';
import { useProject, Project } from '../context/ProjectContext';

const STATUS_COLOR: Record<string, string> = {
    active: '#10B981',
    error: '#EF4444',
    scanning: '#3B82F6',
    analyzing: '#8B5CF6',
};

const AVATAR_COLORS = [
    'linear-gradient(135deg,#6366F1,#4F46E5)',
    'linear-gradient(135deg,#10B981,#059669)',
    'linear-gradient(135deg,#8B5CF6,#7C3AED)',
    'linear-gradient(135deg,#F59E0B,#D97706)',
    'linear-gradient(135deg,#EC4899,#DB2777)',
    'linear-gradient(135deg,#06B6D4,#0891B2)',
];

function getAvatarColor(name: string): string {
    return AVATAR_COLORS[name.charCodeAt(0) % AVATAR_COLORS.length];
}

function ProjectItem({
    project,
    selected,
    onSelect,
}: {
    project: Project;
    selected: boolean;
    onSelect: (p: Project) => void;
}) {
    const initials = project.name.slice(0, 2).toUpperCase();
    const dotColor = STATUS_COLOR[project.status] || '#94A3B8';

    return (
        <button
            onClick={() => onSelect(project)}
            style={{
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '8px 12px',
                border: 'none',
                background: selected ? '#EEF2FF' : 'transparent',
                cursor: 'pointer',
                textAlign: 'left',
                transition: 'background 0.15s',
            }}
            onMouseEnter={e => { if (!selected) e.currentTarget.style.background = '#F8FAFC'; }}
            onMouseLeave={e => { if (!selected) e.currentTarget.style.background = 'transparent'; }}
        >
            {/* Avatar */}
            <div style={{
                width: 28, height: 28, borderRadius: 7, flexShrink: 0,
                background: getAvatarColor(project.name),
                display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
                <span style={{ color: '#fff', fontSize: 10, fontWeight: 700 }}>{initials}</span>
            </div>
            {/* Labels */}
            <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: '#0F172A', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {project.name}
                </div>
                <div style={{ fontSize: 10, color: '#94A3B8', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {project.owner}
                </div>
            </div>
            {/* Status dot + selected indicator */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                {project.is_default && (
                    <span style={{ fontSize: 9, fontWeight: 700, padding: '1px 5px', borderRadius: 4, background: '#F1F5F9', color: '#64748B' }}>
                        DEFAULT
                    </span>
                )}
                <div style={{ width: 6, height: 6, borderRadius: '50%', background: dotColor }} />
                {selected && <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#6366F1' }} />}
            </div>
        </button>
    );
}

export default function ProjectSelector() {
    const { selectedProject, setSelectedProject, projects, loading } = useProject();
    const [open, setOpen] = useState(false);
    const ref = useRef<HTMLDivElement>(null);
    const navigate = useNavigate();

    // Close on outside click
    useEffect(() => {
        function handle(e: MouseEvent) {
            if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
        }
        document.addEventListener('mousedown', handle);
        return () => document.removeEventListener('mousedown', handle);
    }, []);

    const handleSelect = (p: Project) => { setSelectedProject(p); setOpen(false); };
    const handleAll = () => { setSelectedProject(null); setOpen(false); };
    const handleAdd = () => { setOpen(false); navigate('/repositories'); };

    const triggerLabel = selectedProject
        ? `${selectedProject.owner}/${selectedProject.name}`
        : 'All Projects';
    const dotColor = selectedProject ? (STATUS_COLOR[selectedProject.status] || '#94A3B8') : undefined;

    if (loading) {
        return (
            <div style={{
                width: 200, height: 34, borderRadius: 9,
                background: '#F1F5F9', animation: 'pulse 1.5s ease-in-out infinite',
            }} />
        );
    }

    const defaults = projects.filter(p => p.is_default);
    const userProjects = projects.filter(p => !p.is_default);

    return (
        <div ref={ref} style={{ position: 'relative' }}>
            {/* Trigger */}
            <button
                onClick={() => setOpen(o => !o)}
                style={{
                    display: 'flex', alignItems: 'center', gap: 7,
                    padding: '6px 12px', borderRadius: 9,
                    border: `1px solid ${open ? '#A5B4FC' : '#E2E8F0'}`,
                    background: open ? '#F5F3FF' : '#F8FAFC',
                    cursor: 'pointer', fontSize: 12, fontWeight: 600, color: '#0F172A',
                    minWidth: 180, maxWidth: 260,
                    boxShadow: open ? '0 0 0 3px rgba(99,102,241,0.12)' : 'none',
                    transition: 'all 0.15s',
                }}
            >
                <GitBranch size={13} color="#6366F1" style={{ flexShrink: 0 }} />
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {triggerLabel}
                </span>
                {dotColor && (
                    <div style={{ width: 6, height: 6, borderRadius: '50%', background: dotColor, flexShrink: 0 }} />
                )}
                <ChevronDown
                    size={12}
                    color="#94A3B8"
                    style={{
                        flexShrink: 0,
                        transform: open ? 'rotate(180deg)' : 'none',
                        transition: 'transform 0.2s',
                    }}
                />
            </button>

            {/* Dropdown */}
            {open && (
                <div style={{
                    position: 'absolute',
                    top: 'calc(100% + 6px)',
                    left: 0,
                    zIndex: 9999,
                    width: 280,
                    background: '#fff',
                    border: '1px solid #E2E8F0',
                    borderRadius: 14,
                    boxShadow: '0 16px 48px rgba(0,0,0,0.12), 0 4px 12px rgba(0,0,0,0.06)',
                    overflow: 'hidden',
                }}>
                    {/* All Projects */}
                    <div style={{ padding: '8px 8px 6px', borderBottom: '1px solid #F1F5F9' }}>
                        <button
                            onClick={handleAll}
                            style={{
                                width: '100%', display: 'flex', alignItems: 'center', gap: 10,
                                padding: '7px 10px', border: 'none',
                                background: !selectedProject ? '#EEF2FF' : 'transparent',
                                borderRadius: 9, cursor: 'pointer', textAlign: 'left',
                                transition: 'background 0.15s',
                            }}
                            onMouseEnter={e => { if (selectedProject) e.currentTarget.style.background = '#F8FAFC'; }}
                            onMouseLeave={e => { if (selectedProject) e.currentTarget.style.background = 'transparent'; }}
                        >
                            <div style={{
                                width: 28, height: 28, borderRadius: 7, flexShrink: 0,
                                background: 'linear-gradient(135deg,#6366F1,#8B5CF6)',
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                            }}>
                                <Layers size={13} color="#fff" />
                            </div>
                            <div style={{ flex: 1 }}>
                                <div style={{ fontSize: 12, fontWeight: 600, color: !selectedProject ? '#4F46E5' : '#0F172A' }}>
                                    All Projects
                                </div>
                                <div style={{ fontSize: 10, color: '#94A3B8' }}>{projects.length} repositories</div>
                            </div>
                            {!selectedProject && (
                                <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#6366F1', flexShrink: 0 }} />
                            )}
                        </button>
                    </div>

                    {/* Project list */}
                    <div style={{ maxHeight: 260, overflowY: 'auto' }}>
                        {projects.length === 0 ? (
                            <div style={{ padding: '20px 16px', textAlign: 'center', fontSize: 12, color: '#94A3B8' }}>
                                No repositories connected yet
                            </div>
                        ) : (
                            <>
                                {defaults.length > 0 && (
                                    <>
                                        <div style={{ padding: '6px 12px 2px', fontSize: 9, fontWeight: 700, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.08em', background: '#FAFBFF' }}>
                                            Example Projects
                                        </div>
                                        {defaults.map(p => (
                                            <ProjectItem
                                                key={p.id}
                                                project={p}
                                                selected={selectedProject?.id === p.id}
                                                onSelect={handleSelect}
                                            />
                                        ))}
                                    </>
                                )}
                                {userProjects.length > 0 && (
                                    <>
                                        <div style={{ padding: '6px 12px 2px', fontSize: 9, fontWeight: 700, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.08em', background: '#FAFBFF' }}>
                                            Your Repositories
                                        </div>
                                        {userProjects.map(p => (
                                            <ProjectItem
                                                key={p.id}
                                                project={p}
                                                selected={selectedProject?.id === p.id}
                                                onSelect={handleSelect}
                                            />
                                        ))}
                                    </>
                                )}
                            </>
                        )}
                    </div>

                    {/* Footer */}
                    <div style={{ padding: '6px 8px', borderTop: '1px solid #F1F5F9' }}>
                        <button
                            onClick={handleAdd}
                            style={{
                                width: '100%', display: 'flex', alignItems: 'center', gap: 8,
                                padding: '7px 10px', border: 'none', borderRadius: 9,
                                background: 'transparent', cursor: 'pointer',
                                fontSize: 12, fontWeight: 600, color: '#6366F1',
                                transition: 'background 0.15s',
                            }}
                            onMouseEnter={e => { e.currentTarget.style.background = '#EEF2FF'; }}
                            onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; }}
                        >
                            <Plus size={13} />
                            Add Repository
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}
