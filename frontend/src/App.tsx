// frontend/src/App.tsx
import { useState, useEffect, useRef } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Link, useLocation, useNavigate } from 'react-router-dom';
import {
    LayoutDashboard, AlertTriangle, Activity, MessageSquare,
    Settings, LogOut, Bell, Zap, GitBranch, Code2, TrendingUp,
    Menu, Radio, History, X, Flame, Info as InfoIcon,
    CheckCircle, AlertOctagon
} from 'lucide-react';
import ProjectSelector from './components/ProjectSelector';
import PageLoadingBar from './components/PageLoadingBar';
import Dashboard from './pages/Dashboard';
import Incidents from './pages/Incidents';
import IncidentDetail from './pages/IncidentDetail';
import AnomalyMap from './pages/AnomalyMap';
import Repositories from './pages/Repositories';
import Developer from './pages/Developer';
import Predictions from './pages/Predictions';
import SettingsPage from './pages/Settings';
import Chatbot from './pages/Chatbot';
import Login from './pages/Login';
import Pulse from './pages/Pulse';
import IncidentHistory from './pages/IncidentHistory';
import api from './services/api';
import { ProjectProvider, useProject } from './context/ProjectContext';
import { NotificationProvider, useNotifications, Notification } from './context/NotificationContext';
import { ToastProvider } from './context/ToastContext';

const NAV_ITEMS = [
    { path: '/', icon: LayoutDashboard, label: 'Dashboard', exact: true },
    { path: '/incidents', icon: AlertTriangle, label: 'Incidents' },
    { path: '/incidents/history', icon: History, label: 'Incident History' },
    { path: '/repositories', icon: GitBranch, label: 'Repositories' },
    { path: '/developer', icon: Code2, label: 'Developer' },
    { path: '/anomalies', icon: Activity, label: 'Anomaly Map' },
    { path: '/predictions', icon: TrendingUp, label: 'Predictions' },
    { path: '/pulse', icon: Radio, label: 'Pulse' },
];

// ── Notification icon per type ─────────────────────────────────────────────────
function NotifIcon({ type }: { type: string }) {
    const s = 14;
    if (type === 'p1') return <Flame size={s} color="#EF4444" />;
    if (type === 'p2') return <AlertOctagon size={s} color="#F97316" />;
    if (type === 'anomaly') return <Bell size={s} color="#F59E0B" />;
    if (type === 'rca') return <TrendingUp size={s} color="#3B82F6" />;
    if (type === 'resolved') return <CheckCircle size={s} color="#10B981" />;
    return <InfoIcon size={s} color="#6366F1" />;
}

// ── Sidebar ────────────────────────────────────────────────────────────────────
function Sidebar({ activePath, collapsed, onToggle }: { activePath: string; collapsed: boolean; onToggle: () => void }) {
    return (
        <nav style={{
            width: collapsed ? 64 : 240, minHeight: '100vh',
            background: '#FFFFFF',
            borderRight: '1px solid #E2E8F0',
            display: 'flex', flexDirection: 'column',
            padding: '0', position: 'fixed', left: 0, top: 0, zIndex: 50,
            transition: 'width 0.2s ease',
            overflow: 'hidden',
        }}>
            {/* Logo */}
            <div style={{
                height: 64, display: 'flex', alignItems: 'center',
                padding: collapsed ? '0 16px' : '0 20px', gap: 10,
                borderBottom: '1px solid #E2E8F0',
                flexShrink: 0,
            }}>
                <div style={{
                    width: 34, height: 34, borderRadius: 10, flexShrink: 0,
                    background: 'linear-gradient(135deg, #6366F1, #3B82F6)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    boxShadow: '0 4px 12px rgba(99,102,241,0.3)',
                }}>
                    <Zap size={17} color="#fff" />
                </div>
                {!collapsed && (
                    <div>
                        <div style={{ fontWeight: 800, fontSize: 14, color: '#0F172A', letterSpacing: '-0.01em' }}>NeuralOps</div>
                        <div style={{ fontSize: 9.5, color: '#94A3B8', letterSpacing: '0.09em', fontWeight: 600 }}>AI SRE PLATFORM</div>
                    </div>
                )}
            </div>

            {/* Nav items */}
            <div style={{ flex: 1, padding: '12px 8px', display: 'flex', flexDirection: 'column', gap: 2, overflowY: 'auto' }}>
                {NAV_ITEMS.map(({ path, icon: Icon, label, exact }) => {
                    const active = exact ? activePath === path : (activePath === path || activePath.startsWith(path + '/') || activePath === path);
                    // Don't mark /incidents active when on /incidents/history
                    const isActive = path === '/incidents'
                        ? (activePath === '/incidents' || (activePath.startsWith('/incidents/') && !activePath.startsWith('/incidents/history')))
                        : active;
                    return (
                        <Link key={path} to={path} title={collapsed ? label : undefined} style={{ textDecoration: 'none' }}>
                            <div style={{
                                display: 'flex', alignItems: 'center', gap: 10,
                                padding: collapsed ? '10px 13px' : '9px 12px',
                                borderRadius: 8, cursor: 'pointer', transition: 'all 0.15s',
                                background: isActive ? 'rgba(99,102,241,0.08)' : 'transparent',
                                color: isActive ? '#6366F1' : '#64748B',
                                fontWeight: isActive ? 600 : 400,
                                justifyContent: collapsed ? 'center' : 'flex-start',
                            }}>
                                <Icon size={16} style={{ flexShrink: 0 }} />
                                {!collapsed && <span style={{ fontSize: 13 }}>{label}</span>}
                            </div>
                        </Link>
                    );
                })}
            </div>

            {/* Footer */}
            <div style={{ padding: '12px 8px', borderTop: '1px solid #E2E8F0', display: 'flex', flexDirection: 'column', gap: 2 }}>
                <Link to="/settings" title={collapsed ? 'Settings' : undefined} style={{ textDecoration: 'none' }}>
                    <div style={{
                        display: 'flex', alignItems: 'center', gap: 10,
                        padding: collapsed ? '10px 13px' : '9px 12px',
                        borderRadius: 8, color: activePath.startsWith('/settings') ? '#6366F1' : '#64748B', cursor: 'pointer',
                        transition: 'all 0.15s',
                        justifyContent: collapsed ? 'center' : 'flex-start',
                        background: activePath.startsWith('/settings') ? 'rgba(99,102,241,0.08)' : 'transparent',
                        fontWeight: activePath.startsWith('/settings') ? 600 : 400,
                    }}>
                        <Settings size={16} style={{ flexShrink: 0 }} />
                        {!collapsed && <span style={{ fontSize: 13 }}>Settings</span>}
                    </div>
                </Link>
                <div
                    onClick={() => { api.logout(); window.location.href = '/login'; }}
                    title={collapsed ? 'Sign Out' : undefined}
                    style={{
                        display: 'flex', alignItems: 'center', gap: 10,
                        padding: collapsed ? '10px 13px' : '9px 12px',
                        borderRadius: 8, color: '#EF4444', cursor: 'pointer',
                        transition: 'all 0.15s',
                        justifyContent: collapsed ? 'center' : 'flex-start',
                    }}
                    onMouseEnter={e => (e.currentTarget.style.background = '#FEF2F2')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                >
                    <LogOut size={16} style={{ flexShrink: 0 }} />
                    {!collapsed && <span style={{ fontSize: 13 }}>Sign Out</span>}
                </div>
                <button
                    onClick={onToggle}
                    title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
                    style={{
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        padding: '8px', borderRadius: 8, cursor: 'pointer',
                        border: '1px solid #E2E8F0', background: 'transparent',
                        color: '#94A3B8', transition: 'all 0.15s', marginTop: 4,
                    }}
                    onMouseEnter={e => (e.currentTarget.style.background = '#F8FAFC')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                >
                    <Menu size={14} />
                </button>
            </div>
        </nav>
    );
}

// (ProjectDropdown replaced by components/ProjectSelector.tsx)

// ── Notification Bell ──────────────────────────────────────────────────────────
function NotificationBell() {
    const { notifications, unreadCount, dropdownOpen, setDropdownOpen, markRead, markAllRead } = useNotifications();
    const navigate = useNavigate();
    const ref = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) setDropdownOpen(false);
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, [setDropdownOpen]);

    const handleNotifClick = (n: Notification) => {
        markRead(n.id);
        if (n.link) navigate(n.link);
        setDropdownOpen(false);
    };

    return (
        <div ref={ref} style={{ position: 'relative', cursor: 'pointer' }}>
            <div
                onClick={() => setDropdownOpen(!dropdownOpen)}
                style={{
                    width: 36, height: 36, borderRadius: 8,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: dropdownOpen ? '#F1F5F9' : 'transparent',
                    border: '1px solid transparent',
                    transition: 'all 0.15s',
                    position: 'relative',
                }}
                onMouseEnter={e => (e.currentTarget.style.background = '#F1F5F9')}
                onMouseLeave={e => (e.currentTarget.style.background = dropdownOpen ? '#F1F5F9' : 'transparent')}
            >
                <Bell size={18} color="#64748B" />
                {unreadCount > 0 && (
                    <div style={{
                        position: 'absolute', top: 4, right: 4,
                        minWidth: 16, height: 16, borderRadius: 9999,
                        background: '#EF4444', border: '1.5px solid white',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 9, fontWeight: 800, color: '#fff', padding: '0 3px',
                    }}>
                        {unreadCount > 99 ? '99+' : unreadCount}
                    </div>
                )}
            </div>

            {dropdownOpen && (
                <div style={{
                    position: 'absolute', top: '110%', right: 0,
                    background: '#fff', border: '1px solid #E2E8F0',
                    borderRadius: 12, boxShadow: '0 12px 32px rgba(0,0,0,0.12)',
                    zIndex: 1000, width: 360, overflow: 'hidden',
                }}>
                    {/* Header */}
                    <div style={{
                        padding: '14px 16px', borderBottom: '1px solid #E2E8F0',
                        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    }}>
                        <div style={{ fontWeight: 700, fontSize: 13, color: '#0F172A' }}>
                            Notifications {unreadCount > 0 && (
                                <span style={{ marginLeft: 6, background: '#EF4444', color: '#fff', borderRadius: 9999, fontSize: 10, padding: '1px 6px', fontWeight: 800 }}>
                                    {unreadCount}
                                </span>
                            )}
                        </div>
                        {unreadCount > 0 && (
                            <button
                                onClick={markAllRead}
                                style={{ fontSize: 11, color: '#6366F1', background: 'none', border: 'none', cursor: 'pointer', fontWeight: 600 }}
                            >
                                Mark all read
                            </button>
                        )}
                    </div>

                    {/* List */}
                    <div style={{ maxHeight: 380, overflowY: 'auto' }}>
                        {notifications.length === 0 ? (
                            <div style={{ padding: 32, textAlign: 'center', color: '#94A3B8', fontSize: 13 }}>
                                <Bell size={24} color="#CBD5E1" style={{ marginBottom: 8 }} />
                                <div>No notifications yet</div>
                            </div>
                        ) : notifications.map(n => (
                            <div
                                key={n.id}
                                onClick={() => handleNotifClick(n)}
                                style={{
                                    padding: '12px 16px',
                                    background: n.is_read ? 'transparent' : 'rgba(99,102,241,0.04)',
                                    borderBottom: '1px solid #F1F5F9',
                                    cursor: 'pointer',
                                    display: 'flex', gap: 10, alignItems: 'flex-start',
                                    transition: 'background 0.1s',
                                }}
                                onMouseEnter={e => (e.currentTarget.style.background = '#F8FAFC')}
                                onMouseLeave={e => (e.currentTarget.style.background = n.is_read ? 'transparent' : 'rgba(99,102,241,0.04)')}
                            >
                                <div style={{ marginTop: 2, flexShrink: 0 }}>
                                    <NotifIcon type={n.type} />
                                </div>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={{ fontWeight: 600, fontSize: 12, color: '#0F172A', display: 'flex', alignItems: 'center', gap: 6 }}>
                                        {n.title}
                                        {!n.is_read && (
                                            <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#6366F1', flexShrink: 0 }} />
                                        )}
                                    </div>
                                    <div style={{ fontSize: 11, color: '#64748B', marginTop: 2, lineHeight: 1.4 }}>{n.message}</div>
                                    <div style={{ fontSize: 10, color: '#94A3B8', marginTop: 4 }}>
                                        {n.created_at ? new Date(n.created_at).toLocaleString() : ''}
                                    </div>
                                </div>
                                {!n.is_read && (
                                    <button
                                        onClick={e => { e.stopPropagation(); markRead(n.id); }}
                                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94A3B8', padding: 2, flexShrink: 0 }}
                                        title="Mark as read"
                                    >
                                        <X size={12} />
                                    </button>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

// ── TopBar ─────────────────────────────────────────────────────────────────────
function TopBar({ sidebarWidth }: { sidebarWidth: number }) {
    return (
        <div style={{
            height: 64, background: '#FFFFFF',
            borderBottom: '1px solid #E2E8F0',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '0 24px',
            position: 'fixed', top: 0, left: sidebarWidth, right: 0, zIndex: 40,
            transition: 'left 0.2s ease',
        }}>
            <div style={{ fontSize: 13, color: '#94A3B8' }}>
                AI DevOps Intelligence Platform
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <ProjectSelector />
                <NotificationBell />
                <div style={{
                    width: 34, height: 34, borderRadius: '50%',
                    background: 'linear-gradient(135deg, #6366F1, #3B82F6)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 13, fontWeight: 700, color: '#fff', cursor: 'pointer',
                    border: '2px solid #E2E8F0',
                }}>A</div>
            </div>
        </div>
    );
}

// ── Chat sidebar ───────────────────────────────────────────────────────────────
function ChatSidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
    return (
        <div style={{
            position: 'fixed', right: 0, top: 0, bottom: 0,
            width: open ? 380 : 0,
            background: '#FFFFFF',
            borderLeft: '1px solid #E2E8F0',
            zIndex: 45,
            transition: 'width 0.25s ease',
            overflow: 'hidden',
            display: 'flex', flexDirection: 'column',
            boxShadow: open ? '-4px 0 20px rgba(0,0,0,0.06)' : 'none',
        }}>
            {open && <Chatbot embedded onClose={onClose} />}
        </div>
    );
}

// ── AppLayout ──────────────────────────────────────────────────────────────────
function AppLayout() {
    const location = useLocation();
    const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
    const [chatOpen, setChatOpen] = useState(false);
    const sidebarWidth = sidebarCollapsed ? 64 : 240;

    if (!api.isAuthenticated()) return <Navigate to="/login" replace />;

    return (
        <div style={{ display: 'flex', minHeight: '100vh', background: '#F8FAFC' }}>
            <Sidebar
                activePath={location.pathname}
                collapsed={sidebarCollapsed}
                onToggle={() => setSidebarCollapsed(c => !c)}
            />
            <div style={{
                marginLeft: sidebarWidth, flex: 1, display: 'flex', flexDirection: 'column',
                marginRight: chatOpen ? 380 : 0, transition: 'margin 0.2s ease',
                minWidth: 0,
            }}>
                <TopBar sidebarWidth={sidebarWidth} />
                <PageLoadingBar />
                <main style={{ marginTop: 64, padding: 24, flex: 1, minHeight: 0 }}>
                    <Routes>
                        <Route path="/" element={<Dashboard />} />
                        <Route path="/incidents" element={<Incidents />} />
                        <Route path="/incidents/history" element={<IncidentHistory />} />
                        <Route path="/incidents/:id" element={<IncidentDetail />} />
                        <Route path="/repositories" element={<Repositories />} />
                        <Route path="/developer" element={<Developer />} />
                        <Route path="/developer/:repoId" element={<Developer />} />
                        <Route path="/anomalies" element={<AnomalyMap />} />
                        <Route path="/predictions" element={<Predictions />} />
                        <Route path="/pulse" element={<Pulse />} />
                        <Route path="/settings" element={<SettingsPage />} />
                        <Route path="*" element={<Navigate to="/" replace />} />
                    </Routes>
                </main>
            </div>

            {!chatOpen && (
                <button
                    onClick={() => setChatOpen(true)}
                    title="Open AI Assistant"
                    style={{
                        position: 'fixed', bottom: 24, right: 24, zIndex: 46,
                        width: 52, height: 52, borderRadius: '50%',
                        background: 'linear-gradient(135deg, #6366F1, #3B82F6)',
                        border: 'none', cursor: 'pointer',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        boxShadow: '0 8px 24px rgba(99,102,241,0.4)',
                        transition: 'transform 0.15s, box-shadow 0.15s',
                    }}
                    onMouseEnter={e => { (e.target as HTMLElement).style.transform = 'scale(1.08)'; }}
                    onMouseLeave={e => { (e.target as HTMLElement).style.transform = 'scale(1)'; }}
                >
                    <MessageSquare size={22} color="#fff" />
                </button>
            )}

            <ChatSidebar open={chatOpen} onClose={() => setChatOpen(false)} />
        </div>
    );
}

// ── Root App ───────────────────────────────────────────────────────────────────
export default function App() {
    return (
        <BrowserRouter>
            <ProjectProvider>
                <NotificationProvider>
                    <ToastProvider>
                        <Routes>
                            <Route path="/login" element={<Login />} />
                            <Route path="/*" element={<AppLayout />} />
                        </Routes>
                    </ToastProvider>
                </NotificationProvider>
            </ProjectProvider>
        </BrowserRouter>
    );
}
