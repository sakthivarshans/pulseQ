// frontend/src/services/api.ts
// Centralized API client for NeuralOps
// BASE_URL is RELATIVE — all calls go through Vite proxy → backend on :8080
// This avoids CORS entirely in development.

const BASE_URL = '/api/v1';
const TIMEOUT_MS = 20000;

// ────────────────────────────────────────────────────────────────
// Token management
// ────────────────────────────────────────────────────────────────
// Bypass auth: always inject a dev token so no login is required
const DEV_BYPASS_TOKEN = 'dev-bypass-no-auth';
function getToken(): string | null { return localStorage.getItem('neuralops_token') || DEV_BYPASS_TOKEN; }
function setToken(t: string) { localStorage.setItem('neuralops_token', t); }
function clearToken() { localStorage.removeItem('neuralops_token'); }
// Ensure token is always present
if (!localStorage.getItem('neuralops_token')) { localStorage.setItem('neuralops_token', DEV_BYPASS_TOKEN); }

function headers(extra?: Record<string, string>): HeadersInit {
    const token = getToken();
    return {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        'Content-Type': 'application/json',
        ...extra,
    };
}

async function fetchWithTimeout(url: string, opts: RequestInit): Promise<Response> {
    const ctrl = new AbortController();
    const timer = setTimeout(
        () => ctrl.abort(new DOMException(`Request timed out after ${TIMEOUT_MS}ms`, 'TimeoutError')),
        TIMEOUT_MS
    );
    try {
        const res = await fetch(url, { ...opts, signal: ctrl.signal });
        return res;
    } finally {
        clearTimeout(timer);
    }
}

async function get<T>(path: string): Promise<T> {
    const res = await fetchWithTimeout(`${BASE_URL}${path}`, { method: 'GET', headers: headers() });
    if (!res.ok) throw new Error(`API ${res.status}`);
    return res.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
    const res = await fetchWithTimeout(`${BASE_URL}${path}`, { method: 'POST', headers: headers(), body: JSON.stringify(body) });
    if (!res.ok) throw new Error(`API ${res.status}`);
    return res.json();
}

async function del(path: string): Promise<void> {
    await fetchWithTimeout(`${BASE_URL}${path}`, { method: 'DELETE', headers: headers() });
}

// ────────────────────────────────────────────────────────────────
// Auth
// ────────────────────────────────────────────────────────────────
const api = {
    isAuthenticated(): boolean { return true; }, // Auth bypass: always authenticated

    async login(email: string, password: string): Promise<void> {
        // Support both email login (via JSON) and legacy username/password form (via form-data)
        const isEmail = email.includes('@');
        const usernameToSend = isEmail ? email : email; // backend accepts both formats

        // Try OAuth2 form submission first (what FastAPI /token endpoint expects)
        const form = new URLSearchParams();
        form.append('username', usernameToSend);
        form.append('password', password);
        const res = await fetchWithTimeout(`/api/v1/auth/token`, {
            method: 'POST',
            body: form.toString(),
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        });
        if (!res.ok) throw new Error('Invalid credentials');
        const data = await res.json();
        setToken(data.access_token);
    },

    logout(): void { clearToken(); },

    // ────────────────────────────────────────────────────────────
    // Dashboard
    // ────────────────────────────────────────────────────────────
    async getSummary(): Promise<any> {
        return get('/dashboard/summary');
    },

    // ────────────────────────────────────────────────────────────
    // Incidents
    // ────────────────────────────────────────────────────────────
    async getIncidents(params: { status?: string; severity?: string; limit?: number; offset?: number; project_id?: string } = {}): Promise<{ incidents: any[]; total: number }> {
        const qs = new URLSearchParams();
        if (params.status) qs.set('status', params.status);
        if (params.severity) qs.set('severity', params.severity);
        if (params.limit) qs.set('limit', String(params.limit));
        if (params.offset) qs.set('offset', String(params.offset));
        if (params.project_id) qs.set('project_id', params.project_id);
        return get(`/incidents?${qs}`);
    },

    async getIncident(id: string): Promise<any> {
        return get(`/incidents/${id}`);
    },

    // ────────────────────────────────────────────────────────────
    // Anomalies
    // ────────────────────────────────────────────────────────────
    async getAnomalies(params: { service?: string; limit?: number; project_id?: string } = {}): Promise<{ anomalies: any[] }> {
        const qs = new URLSearchParams();
        if (params.service) qs.set('service_name', params.service);
        if (params.limit) qs.set('limit', String(params.limit));
        if (params.project_id) qs.set('project_id', params.project_id);
        return get(`/anomalies?${qs}`);
    },

    // ────────────────────────────────────────────────────────────
    // Repositories
    // ────────────────────────────────────────────────────────────
    async getRepositoriesList(): Promise<{ repositories: any[]; total: number }> {
        return get('/repositories/list');
    },

    // ────────────────────────────────────────────────────────────
    // RCA
    // ────────────────────────────────────────────────────────────
    async getRCA(incidentId: string): Promise<any> {
        return get(`/incidents/${incidentId}/rca`);
    },

    // ────────────────────────────────────────────────────────────
    // Audit / actions
    // ────────────────────────────────────────────────────────────
    async getAuditLogs(params: { incident_id?: string; limit?: number } = {}): Promise<any[]> {
        const qs = new URLSearchParams();
        if (params.incident_id) qs.set('incident_id', params.incident_id);
        if (params.limit) qs.set('limit', String(params.limit));
        return get(`/actions/audit?${qs}`);
    },

    // ────────────────────────────────────────────────────────────
    // Metrics (time-series)
    // ────────────────────────────────────────────────────────────
    async getMetrics(service: string, metric: string, from?: number, to?: number, resolution?: string): Promise<any[]> {
        const qs = new URLSearchParams({ metric });
        if (from) qs.set('from', String(from));
        if (to) qs.set('to', String(to));
        if (resolution) qs.set('resolution', resolution);
        try { return get(`/metrics/${service}?${qs}`); } catch { return []; }
    },

    // ────────────────────────────────────────────────────────────
    // Repositories
    // ────────────────────────────────────────────────────────────
    async getRepositories(): Promise<any[]> {
        try { return get('/repositories'); } catch { return []; }
    },

    async getRepository(id: string): Promise<any> {
        return get(`/repositories/${id}`);
    },

    async addRepository(url: string, token?: string): Promise<any> {
        return post('/repositories', { url, token });
    },

    async rescanRepository(id: string): Promise<any> {
        return post(`/repositories/${encodeURIComponent(id)}/rescan`, {});
    },

    async deleteRepository(id: string): Promise<void> {
        return del(`/repositories/${id}`);
    },

    async getRepoAnalysis(id: string): Promise<any> {
        return get(`/repositories/${encodeURIComponent(id)}/analysis`);
    },

    async getRepoIssues(id: string): Promise<any> {
        try { return get(`/repositories/${encodeURIComponent(id)}/issues`); } catch { return { issues: [], total: 0 }; }
    },

    async getRepoLogs(id: string): Promise<any> {
        try { return get(`/repositories/${encodeURIComponent(id)}/logs`); } catch { return { logs: [] }; }
    },

    async submitIssueFeedback(repoId: string, issueId: string, feedback: 'upvote' | 'downvote'): Promise<any> {
        try { return post(`/repositories/${encodeURIComponent(repoId)}/issues/${issueId}/feedback`, { feedback }); } catch { return {}; }
    },

    async getIssueFeedback(repoId: string, issueId: string): Promise<{ upvotes: number; downvotes: number }> {
        try { return get(`/repositories/${encodeURIComponent(repoId)}/issues/${issueId}/feedback/counts`); } catch { return { upvotes: 0, downvotes: 0 }; }
    },

    // ── MongoDB error endpoints (new) ──────────────────────────────────────
    async getRepoErrors(repoId: string, filters?: { severity?: string; error_type?: string; resolved?: boolean }): Promise<any> {
        const qs = new URLSearchParams();
        if (filters?.severity) qs.set('severity', filters.severity);
        if (filters?.error_type) qs.set('error_type', filters.error_type);
        if (filters?.resolved !== undefined) qs.set('resolved', String(filters.resolved));
        const q = qs.toString();
        try { return get(`/repositories/${encodeURIComponent(repoId)}/errors${q ? '?' + q : ''}`); } catch { return { errors: [], total: 0 }; }
    },

    async submitErrorFeedback(repoId: string, errorId: string, feedback: 'upvote' | 'downvote'): Promise<any> {
        try { return post(`/repositories/${encodeURIComponent(repoId)}/errors/${errorId}/feedback`, { feedback }); } catch { return {}; }
    },

    async resolveError(repoId: string, errorId: string): Promise<any> {
        const token = getToken();
        try {
            const res = await fetchWithTimeout(`/api/v1/repositories/${encodeURIComponent(repoId)}/errors/${errorId}/resolve`, {
                method: 'PUT',
                headers: headers(),
            });
            if (!res.ok) throw new Error(`API ${res.status}`);
            return res.json();
        } catch { return {}; }
    },

    // ────────────────────────────────────────────────────────────
    // System Metrics (real psutil)
    // ────────────────────────────────────────────────────────────
    async getSystemMetrics(limit?: number): Promise<any> {
        const qs = limit ? `?limit=${limit}` : '';
        try { return get(`/metrics/system${qs}`); } catch { return { latest: {}, history: [] }; }
    },

    // ────────────────────────────────────────────────────────────
    // Health checks
    // ────────────────────────────────────────────────────────────
    async getSystemHealth(): Promise<any> {
        try {
            const res = await fetchWithTimeout(`/health`, { method: 'GET', headers: headers() });
            if (!res.ok) throw new Error(`API ${res.status}`);
            return res.json();
        } catch { return { status: 'error', services: {}, error: 'API unreachable' }; }
    },

    async getLLMHealth(): Promise<{ openrouter: any; phi3: any; active_model: string; test_response?: string }> {
        try { return get('/health/llm'); } catch { return { openrouter: { available: false }, phi3: { available: false }, active_model: 'none' }; }
    },

    async getGeminiHealth(): Promise<{ connected: boolean; provider?: string; error?: string }> {
        // Backward compat alias — maps OpenRouter status to the old connected/provider shape
        try {
            const r: any = await get('/health/llm');
            const or = r?.openrouter ?? {};
            return {
                connected: or.available ?? false,
                provider: or.available ? r.active_model : undefined,
                error: or.available ? undefined : (or.error ?? 'OpenRouter unavailable'),
            };
        } catch { return { connected: false, error: 'API unreachable' }; }
    },

    async getPhi3Health(): Promise<{ status: string; model?: string; response_time_ms?: number; install_command?: string; error?: string }> {
        try { return get('/health/phi3'); } catch { return { status: 'unreachable', error: 'API unreachable' }; }
    },

    async getChatbotHealth(): Promise<{ gemini_available: boolean; phi3_available: boolean; active_model: string; test_response?: string }> {
        try { return get('/chatbot/health'); } catch { return { gemini_available: false, phi3_available: false, active_model: 'none' }; }
    },

    async getRLStats(): Promise<{ accuracy: number; total: number; last_trained: string | null }> {
        try { return get('/settings/rl-stats'); } catch { return { accuracy: 0.85, total: 0, last_trained: null }; }
    },

    async getIntegrations(): Promise<any> {
        try { return get('/settings/integrations'); } catch { return {}; }
    },

    // ────────────────────────────────────────────────────────────
    // Predictions
    // ────────────────────────────────────────────────────────────
    async getPredictions(): Promise<any[]> {
        try { return get('/predictions'); } catch { return []; }
    },

    // ────────────────────────────────────────────────────────────
    // Chatbot (Streaming SSE)
    // ────────────────────────────────────────────────────────────
    async sendChatMessage(message: string, sessionId?: string, incidentId?: string): Promise<Response> {
        const token = getToken();
        const body: Record<string, unknown> = { message };
        if (sessionId) body.session_id = sessionId;
        if (incidentId) body.incident_id = incidentId;

        return fetch(`/api/v1/chatbot/stream`, {
            method: 'POST',
            headers: {
                ...(token ? { Authorization: `Bearer ${token}` } : {}),
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(body),
        });
    },

    async sendChatMessageREST(message: string, sessionId?: string): Promise<{ session_id: string; message: string; done: boolean }> {
        return post('/chatbot/message', { message, session_id: sessionId });
    },

    async sendChatFeedback(sessionId: string, messageIndex: number, positive: boolean): Promise<void> {
        try { await post('/chatbot/feedback', { session_id: sessionId, message_index: messageIndex, positive }); } catch { /* optional */ }
    },

    // ────────────────────────────────────────────────────────────
    // Settings
    // ────────────────────────────────────────────────────────────
    async getSettings(): Promise<any> {
        try { return get('/settings'); } catch { return {}; }
    },

    async updateSettings(data: Record<string, unknown>): Promise<any> {
        return post('/settings', data);
    },

    // ─────────────────────────────────────────────────────────────
    // Generic helpers (for new pages that call api.get/post/put directly)
    // ─────────────────────────────────────────────────────────────
    async get<T = any>(path: string): Promise<T> {
        const fullPath = path.startsWith('/api/v1') ? path.replace('/api/v1', '') : path;
        return get<T>(fullPath);
    },

    async post<T = any>(path: string, body: unknown): Promise<T> {
        const fullPath = path.startsWith('/api/v1') ? path.replace('/api/v1', '') : path;
        return post<T>(fullPath, body);
    },

    async put<T = any>(path: string, body: unknown): Promise<T> {
        const fullPath = path.startsWith('/api/v1') ? path.replace('/api/v1', '') : path;
        const res = await fetchWithTimeout(`${BASE_URL}${fullPath}`, {
            method: 'PUT',
            headers: headers(),
            body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error(`API ${res.status}`);
        return res.json();
    },
};

export default api;
