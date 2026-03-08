// frontend/src/App.tsx
import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Link, useLocation } from 'react-router-dom';
import {
    LayoutDashboard, AlertTriangle, Activity, MessageSquare,
    Settings, LogOut, Bell, Zap, GitBranch, Code2, TrendingUp,
    ChevronDown, X, Menu
} from 'lucide-react';
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
import api from './services/api';

const NAV_ITEMS = [
    { path: '/', icon: LayoutDashboard, label: 'Dashboard', exact: true },
    { path: '/incidents', icon: AlertTriangle, label: 'Incidents' },
    { path: '/repositories', icon: GitBranch, label: 'Repositories' },
    { path: '/developer', icon: Code2, label: 'Developer' },
    { path: '/anomalies', icon: Activity, label: 'Anomaly Map' },
    { path: '/predictions', icon: TrendingUp, label: 'Predictions' },
];

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
                    const active = exact ? activePath === path : (activePath === path || activePath.startsWith(path));
                    return (
                        <Link key={path} to={path} title={collapsed ? label : undefined} style={{ textDecoration: 'none' }}>
                            <div style={{
                                display: 'flex', alignItems: 'center', gap: 10,
                                padding: collapsed ? '10px 13px' : '9px 12px',
                                borderRadius: 8, cursor: 'pointer', transition: 'all 0.15s',
                                background: active ? 'rgba(99,102,241,0.08)' : 'transparent',
                                color: active ? '#6366F1' : '#64748B',
                                fontWeight: active ? 600 : 400,
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
                        borderRadius: 8, color: '#64748B', cursor: 'pointer',
                        transition: 'all 0.15s',
                        justifyContent: collapsed ? 'center' : 'flex-start',
                        background: activePath.startsWith('/settings') ? 'rgba(99,102,241,0.08)' : 'transparent',
                        fontWeight: activePath.startsWith('/settings') ? 600 : 400,
                        color2: activePath.startsWith('/settings') ? '#6366F1' : '#64748B',
                    } as any}>
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
                {/* Collapse toggle */}
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

function TopBar({ sidebarWidth }: { sidebarWidth: number }) {
    const [hasNotif, setHasNotif] = useState(true);
    return (
        <div style={{
            height: 64, background: '#FFFFFF',
            borderBottom: '1px solid #E2E8F0',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '0 24px',
            position: 'fixed', top: 0, left: sidebarWidth, right: 0, zIndex: 40,
            transition: 'left 0.2s ease',
        }}>
            {/* Left: breadcrumb handled per page */}
            <div style={{ fontSize: 13, color: '#94A3B8' }}>
                AI DevOps Intelligence Platform
            </div>
            {/* Right */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                {/* Notification bell */}
                <div style={{ position: 'relative', cursor: 'pointer' }}>
                    <Bell size={18} color="#64748B" />
                    {hasNotif && (
                        <div style={{
                            position: 'absolute', top: -1, right: -1,
                            width: 7, height: 7, borderRadius: '50%',
                            background: '#EF4444', border: '1.5px solid white',
                        }} />
                    )}
                </div>
                {/* User avatar */}
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

// Chatbot sidebar wrapper — shows on all pages if open
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
                <main style={{ marginTop: 64, padding: 24, flex: 1, minHeight: 0 }}>
                    <Routes>
                        <Route path="/" element={<Dashboard />} />
                        <Route path="/incidents" element={<Incidents />} />
                        <Route path="/incidents/:id" element={<IncidentDetail />} />
                        <Route path="/repositories" element={<Repositories />} />
                        <Route path="/developer" element={<Developer />} />
                        <Route path="/developer/:repoId" element={<Developer />} />
                        <Route path="/anomalies" element={<AnomalyMap />} />
                        <Route path="/predictions" element={<Predictions />} />
                        <Route path="/settings" element={<SettingsPage />} />
                        <Route path="*" element={<Navigate to="/" replace />} />
                    </Routes>
                </main>
            </div>

            {/* Floating chatbot toggle button */}
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

export default function App() {
    return (
        <BrowserRouter>
            <Routes>
                <Route path="/login" element={<Navigate to="/" replace />} />
                <Route path="/*" element={<AppLayout />} />
            </Routes>
        </BrowserRouter>
    );
}
