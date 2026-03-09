// frontend/src/context/ToastContext.tsx
import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import { AlertTriangle, CheckCircle, Bell, TrendingUp, Info } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export type ToastType = 'p1' | 'p2' | 'resolved' | 'anomaly' | 'rca' | 'info';

export interface Toast {
    id: string;
    type: ToastType;
    title: string;
    message: string;
    link?: string;
    duration?: number; // ms, default 8000 for P1, 5000 others
}

interface ToastContextType {
    addToast: (t: Omit<Toast, 'id'>) => void;
    removeToast: (id: string) => void;
}

const ToastContext = createContext<ToastContextType>({
    addToast: () => { },
    removeToast: () => { },
});

const TOAST_COLORS: Record<ToastType, { bg: string; border: string; icon: string }> = {
    p1: { bg: '#FEF2F2', border: '#EF4444', icon: '#EF4444' },
    p2: { bg: '#FFF7ED', border: '#F97316', icon: '#F97316' },
    resolved: { bg: '#ECFDF5', border: '#10B981', icon: '#10B981' },
    anomaly: { bg: '#FFFBEB', border: '#F59E0B', icon: '#F59E0B' },
    rca: { bg: '#EFF6FF', border: '#3B82F6', icon: '#3B82F6' },
    info: { bg: '#F8FAFC', border: '#94A3B8', icon: '#6366F1' },
};

function ToastIcon({ type }: { type: ToastType }) {
    const color = TOAST_COLORS[type].icon;
    const size = 18;
    switch (type) {
        case 'p1': case 'p2': return <AlertTriangle size={size} color={color} />;
        case 'resolved': return <CheckCircle size={size} color={color} />;
        case 'anomaly': return <Bell size={size} color={color} />;
        case 'rca': return <TrendingUp size={size} color={color} />;
        default: return <Info size={size} color={color} />;
    }
}

function ToastItem({ toast, onRemove }: { toast: Toast; onRemove: () => void }) {
    const navigate = useNavigate();
    const s = TOAST_COLORS[toast.type];
    const [visible, setVisible] = useState(false);

    useEffect(() => {
        setTimeout(() => setVisible(true), 10);
    }, []);

    return (
        <div
            style={{
                background: s.bg,
                border: `1px solid ${s.border}`,
                borderLeft: `4px solid ${s.border}`,
                borderRadius: 10,
                padding: '14px 16px',
                minWidth: 320,
                maxWidth: 380,
                boxShadow: '0 8px 24px rgba(0,0,0,0.12)',
                display: 'flex',
                gap: 12,
                alignItems: 'flex-start',
                cursor: toast.link ? 'pointer' : 'default',
                transform: visible ? 'translateX(0)' : 'translateX(120px)',
                opacity: visible ? 1 : 0,
                transition: 'transform 0.3s ease, opacity 0.3s ease',
            }}
            onClick={() => {
                if (toast.link) navigate(toast.link);
                onRemove();
            }}
        >
            <div style={{ flexShrink: 0, marginTop: 1 }}>
                <ToastIcon type={toast.type} />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: 13, color: '#0F172A', marginBottom: 2 }}>
                    {toast.title}
                </div>
                <div style={{ fontSize: 12, color: '#64748B', lineHeight: 1.4 }}>
                    {toast.message}
                </div>
            </div>
            <button
                onClick={e => { e.stopPropagation(); onRemove(); }}
                style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 2, color: '#94A3B8', flexShrink: 0 }}
            >
                ×
            </button>
        </div>
    );
}

export function ToastContainer({ toasts, onRemove }: { toasts: Toast[]; onRemove: (id: string) => void }) {
    return (
        <div style={{
            position: 'fixed',
            bottom: 24,
            right: 24,
            zIndex: 9999,
            display: 'flex',
            flexDirection: 'column',
            gap: 10,
            pointerEvents: 'none',
        }}>
            {toasts.map(t => (
                <div key={t.id} style={{ pointerEvents: 'all' }}>
                    <ToastItem toast={t} onRemove={() => onRemove(t.id)} />
                </div>
            ))}
        </div>
    );
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
    const [toasts, setToasts] = useState<Toast[]>([]);
    const timers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

    const removeToast = useCallback((id: string) => {
        setToasts(prev => prev.filter(t => t.id !== id));
        const timer = timers.current.get(id);
        if (timer) { clearTimeout(timer); timers.current.delete(id); }
    }, []);

    const addToast = useCallback((t: Omit<Toast, 'id'>) => {
        const id = `toast_${Date.now()}_${Math.random().toString(36).slice(2)}`;
        const duration = t.duration ?? (t.type === 'p1' ? 8000 : 5000);
        setToasts(prev => [...prev.slice(-4), { ...t, id }]); // max 5 toasts
        const timer = setTimeout(() => removeToast(id), duration);
        timers.current.set(id, timer);
    }, [removeToast]);

    return (
        <ToastContext.Provider value={{ addToast, removeToast }}>
            {children}
            <ToastContainer toasts={toasts} onRemove={removeToast} />
        </ToastContext.Provider>
    );
}

export const useToast = () => useContext(ToastContext);
