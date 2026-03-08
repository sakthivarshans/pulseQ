/**
 * frontend/src/hooks/useWebSocket.ts
 * ─────────────────────────────────────
 * Reconnecting WebSocket hook with exponential backoff.
 * Handles server-sent ping frames by replying with pong.
 * Exposes `connected` state and a `send` function.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

export interface WSMessage {
    type: string;
    [key: string]: unknown;
}

export function useWebSocket(
    path: string,
    onMessage: (data: WSMessage) => void
) {
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
    const attemptsRef = useRef(0);
    const [connected, setConnected] = useState(false);
    // Always use the latest callback without re-creating the WebSocket
    const onMessageRef = useRef(onMessage);
    onMessageRef.current = onMessage;

    const getToken = (): string => {
        // Try cookie first, then localStorage
        const cookieMatch = document.cookie.match(/(?:^|;\s*)access_token=([^;]+)/);
        if (cookieMatch) return cookieMatch[1];
        return localStorage.getItem('access_token') ?? '';
    };

    const connect = useCallback(() => {
        // Clear any existing reconnect timer
        clearTimeout(reconnectTimerRef.current);

        try {
            const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const host = window.location.host;
            const token = getToken();
            const url = `${proto}//${host}${path}${token ? `?token=${encodeURIComponent(token)}` : ''}`;

            const ws = new WebSocket(url);
            wsRef.current = ws;

            ws.onopen = () => {
                setConnected(true);
                attemptsRef.current = 0;
            };

            ws.onmessage = (event: MessageEvent) => {
                try {
                    const data: WSMessage = JSON.parse(event.data as string);
                    // Respond to server keepalive pings
                    if (data.type === 'ping') {
                        ws.send(JSON.stringify({ type: 'pong' }));
                        return;
                    }
                    onMessageRef.current(data);
                } catch {
                    // Ignore unparseable frames
                }
            };

            ws.onclose = () => {
                setConnected(false);
                wsRef.current = null;
                // Exponential backoff capped at 30 seconds
                const delay = Math.min(1000 * Math.pow(2, attemptsRef.current), 30_000);
                attemptsRef.current += 1;
                reconnectTimerRef.current = setTimeout(connect, delay);
            };

            ws.onerror = () => {
                // Let onclose handle the reconnect
                ws.close();
            };
        } catch {
            const delay = Math.min(1000 * Math.pow(2, attemptsRef.current), 30_000);
            attemptsRef.current += 1;
            reconnectTimerRef.current = setTimeout(connect, delay);
        }
    }, [path]);

    useEffect(() => {
        connect();
        return () => {
            clearTimeout(reconnectTimerRef.current);
            wsRef.current?.close();
            wsRef.current = null;
        };
    }, [connect]);

    const send = useCallback((data: unknown): boolean => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify(data));
            return true;
        }
        return false;
    }, []);

    return { connected, send, attempts: attemptsRef.current };
}
