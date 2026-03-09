// frontend/src/context/NotificationContext.tsx
import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import api from '../services/api';

export interface Notification {
    id: string;
    type: string;
    title: string;
    message: string;
    link?: string | null;
    is_read: boolean;
    created_at: string;
}

interface NotificationContextType {
    notifications: Notification[];
    unreadCount: number;
    dropdownOpen: boolean;
    setDropdownOpen: (o: boolean) => void;
    markRead: (id: string) => Promise<void>;
    markAllRead: () => Promise<void>;
    reload: () => Promise<void>;
}

const NotificationContext = createContext<NotificationContextType>({
    notifications: [],
    unreadCount: 0,
    dropdownOpen: false,
    setDropdownOpen: () => { },
    markRead: async () => { },
    markAllRead: async () => { },
    reload: async () => { },
});

export function NotificationProvider({ children }: { children: React.ReactNode }) {
    const [notifications, setNotifications] = useState<Notification[]>([]);
    const [unreadCount, setUnreadCount] = useState(0);
    const [dropdownOpen, setDropdownOpen] = useState(false);
    const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

    const fetchNotifications = useCallback(async () => {
        try {
            const baseUrl = (import.meta.env.VITE_API_URL || 'http://localhost:8080');
            const token = localStorage.getItem('neuralops_token');
            const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
            const res = await fetch(`${baseUrl}/api/v1/notifications?limit=30`, { headers });
            if (res.ok) {
                const data = await res.json();
                setNotifications(data.notifications || []);
                setUnreadCount(data.unread_count || 0);
            }
        } catch {
            // API offline
        }
    }, []);

    useEffect(() => {
        fetchNotifications();
        pollRef.current = setInterval(fetchNotifications, 30000);
        return () => {
            if (pollRef.current) clearInterval(pollRef.current);
        };
    }, [fetchNotifications]);

    const markRead = async (id: string) => {
        try {
            const baseUrl = (import.meta.env.VITE_API_URL || 'http://localhost:8080');
            const token = localStorage.getItem('neuralops_token');
            const headers: Record<string, string> = { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
            await fetch(`${baseUrl}/api/v1/notifications/${id}/read`, { method: 'POST', headers });
            setNotifications(prev => prev.map(n => n.id === id ? { ...n, is_read: true } : n));
            setUnreadCount(prev => Math.max(0, prev - 1));
        } catch { /* ignore */ }
    };

    const markAllRead = async () => {
        try {
            const baseUrl = (import.meta.env.VITE_API_URL || 'http://localhost:8080');
            const token = localStorage.getItem('neuralops_token');
            const headers: Record<string, string> = { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
            await fetch(`${baseUrl}/api/v1/notifications/read-all`, { method: 'POST', headers });
            setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
            setUnreadCount(0);
        } catch { /* ignore */ }
    };

    return (
        <NotificationContext.Provider value={{
            notifications, unreadCount, dropdownOpen, setDropdownOpen,
            markRead, markAllRead, reload: fetchNotifications,
        }}>
            {children}
        </NotificationContext.Provider>
    );
}

export const useNotifications = () => useContext(NotificationContext);
