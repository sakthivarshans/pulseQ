// frontend/src/pages/Pulse.tsx
// Full integrations management page — all 11 integration types
import { useState, useEffect } from 'react';
import {
    Radio, Cloud, Github, Slack, BellRing, Trello,
    BarChart2, Zap, ChevronRight, Save, RefreshCw,
    CheckCircle, AlertTriangle, Circle,
    GitBranch, Globe, Server, Database, Activity
} from 'lucide-react';
import api from '../services/api';

const INTEGRATIONS = [
    { key: 'aws', label: 'AWS', icon: Cloud, category: 'Cloud' },
    { key: 'azure', label: 'Azure', icon: Cloud, category: 'Cloud' },
    { key: 'gcp', label: 'GCP', icon: Server, category: 'Cloud' },
    { key: 'github', label: 'GitHub', icon: Github, category: 'DevOps' },
    { key: 'gitlab', label: 'GitLab', icon: GitBranch, category: 'DevOps' },
    { key: 'slack', label: 'Slack', icon: Slack, category: 'Alerts' },
    { key: 'pagerduty', label: 'PagerDuty', icon: BellRing, category: 'Alerts' },
    { key: 'jira', label: 'Jira', icon: Trello, category: 'Project' },
    { key: 'datadog', label: 'Datadog', icon: BarChart2, category: 'Observability' },
    { key: 'newrelic', label: 'New Relic', icon: Activity, category: 'Observability' },
    { key: 'webhook', label: 'Custom Webhook', icon: Globe, category: 'Other' },
];

type StatusType = 'configured' | 'not_configured' | 'error';

interface IntegrationMeta {
    type: string;
    is_configured: boolean;
    last_test_status?: string | null;
    last_tested_at?: string | null;
    last_test_error?: string | null;
}

const FIELD_DEFS: Record<string, Array<{ key: string; label: string; type?: string; placeholder?: string; hint?: string }>> = {
    aws: [
        { key: 'access_key_id', label: 'Access Key ID', placeholder: 'AKIA...' },
        { key: 'secret_access_key', label: 'Secret Access Key', type: 'password', placeholder: '••••••••' },
        { key: 'default_region', label: 'Default Region', placeholder: 'us-east-1' },
        { key: 'cloudwatch_log_group', label: 'CloudWatch Log Group', placeholder: '/my-service/logs', hint: 'Optional' },
    ],
    azure: [
        { key: 'tenant_id', label: 'Tenant ID', placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx' },
        { key: 'client_id', label: 'Client ID', placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx' },
        { key: 'client_secret', label: 'Client Secret', type: 'password', placeholder: '••••••••' },
        { key: 'subscription_id', label: 'Subscription ID', placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx' },
        { key: 'resource_group', label: 'Resource Group', placeholder: 'my-resource-group', hint: 'Optional' },
    ],
    gcp: [
        { key: 'project_id', label: 'Project ID', placeholder: 'my-gcp-project' },
        { key: 'default_region', label: 'Default Region', placeholder: 'us-central1' },
        { key: 'service_account_json', label: 'Service Account JSON', type: 'textarea', placeholder: '{"type":"service_account",...}', hint: 'Paste the full service account JSON key file content' },
    ],
    github: [
        { key: 'personal_access_token', label: 'Personal Access Token', type: 'password', placeholder: 'ghp_••••••••', hint: 'Needs repo, admin:org read scopes' },
        { key: 'organization', label: 'Organization', placeholder: 'my-org', hint: 'Optional — leave blank for personal repos' },
    ],
    gitlab: [
        { key: 'personal_access_token', label: 'Personal Access Token', type: 'password', placeholder: 'glpat-••••••', hint: 'Needs read_api, read_repository scopes' },
        { key: 'gitlab_url', label: 'GitLab URL', placeholder: 'https://gitlab.com', hint: 'Change for self-hosted installations' },
        { key: 'group_id', label: 'Group ID', placeholder: '12345', hint: 'Optional — leave blank for personal repos' },
    ],
    slack: [
        { key: 'bot_token', label: 'Bot Token', type: 'password', placeholder: 'xoxb-••••••', hint: 'OAuth token from your Slack App page (Bot Token)' },
        { key: 'alerts_channel', label: 'Alerts Channel', placeholder: '#neuralops-alerts' },
        { key: 'signing_secret', label: 'Signing Secret', type: 'password', placeholder: '••••••••', hint: 'Optional — for verifying incoming webhooks' },
    ],
    pagerduty: [
        { key: 'api_key', label: 'API Key', type: 'password', placeholder: '••••••••', hint: 'User API key from PagerDuty account settings' },
        { key: 'service_key', label: 'Integration Key', placeholder: '••••••••', hint: 'Events API v2 integration key for incident creation' },
        { key: 'from_email', label: 'From Email', placeholder: 'alerts@company.com' },
    ],
    jira: [
        { key: 'jira_url', label: 'Jira URL', placeholder: 'https://your-org.atlassian.net' },
        { key: 'email', label: 'Email', placeholder: 'your-email@company.com' },
        { key: 'api_token', label: 'API Token', type: 'password', placeholder: '••••••••', hint: 'Create at id.atlassian.com/manage-profile/security/api-tokens' },
        { key: 'project_key', label: 'Project Key', placeholder: 'OPS' },
    ],
    datadog: [
        { key: 'api_key', label: 'API Key', type: 'password', placeholder: '••••••••' },
        { key: 'application_key', label: 'Application Key', type: 'password', placeholder: '••••••••', hint: 'Optional — needed for some endpoints' },
        { key: 'site', label: 'Datadog Site', placeholder: 'datadoghq.com', hint: 'e.g. datadoghq.com, datadoghq.eu, us3.datadoghq.com' },
    ],
    newrelic: [
        { key: 'api_key', label: 'API Key', type: 'password', placeholder: 'NRAK-••••••', hint: 'User API key from api.newrelic.com' },
        { key: 'account_id', label: 'Account ID', placeholder: '1234567' },
        { key: 'region', label: 'Region', placeholder: 'US', hint: 'US or EU' },
    ],
    webhook: [
        { key: 'webhook_url', label: 'Webhook URL', placeholder: 'https://example.com/hooks/neuralops' },
        { key: 'http_method', label: 'HTTP Method', placeholder: 'POST', hint: 'POST or GET' },
        { key: 'secret_key', label: 'Secret / HMAC Key', type: 'password', placeholder: '••••••••', hint: 'Optional — used for HMAC signature verification' },
    ],
};

function StatusDot({ status }: { status: StatusType }) {
    const colors: Record<StatusType, string> = {
        configured: '#10B981',
        not_configured: '#CBD5E1',
        error: '#EF4444',
    };
    return (
        <div style={{
            width: 8, height: 8, borderRadius: '50%',
            background: colors[status],
            boxShadow: status === 'configured' ? '0 0 0 3px rgba(16,185,129,0.2)' : 'none',
            flexShrink: 0,
        }} />
    );
}

export default function Pulse() {
    const [selected, setSelected] = useState<string>('aws');
    const [listMeta, setListMeta] = useState<Record<string, IntegrationMeta>>({});
    const [formData, setFormData] = useState<Record<string, string>>({});
    const [saving, setSaving] = useState(false);
    const [testing, setTesting] = useState(false);
    const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
    const [savedMsg, setSavedMsg] = useState('');

    // Load integration statuses
    useEffect(() => {
        (async () => {
            try {
                const data = await (api as any).get('/api/v1/integrations') as any;
                const meta: Record<string, IntegrationMeta> = {};
                for (const item of (data.integrations || [])) meta[item.type] = item;
                setListMeta(meta);
            } catch { /* offline */ }
        })();
    }, []);

    // Load config when selection changes
    useEffect(() => {
        setFormData({});
        setTestResult(null);
        setSavedMsg('');
        (async () => {
            try {
                const data = await (api as any).get(`/api/v1/integrations/${selected}`) as any;
                if (data.config) setFormData(data.config);
            } catch { /* offline or not configured */ }
        })();
    }, [selected]);

    const handleSave = async () => {
        setSaving(true);
        setSavedMsg('');
        try {
            await (api as any).post(`/api/v1/integrations/${selected}`, { config: formData });
            setSavedMsg('Saved successfully!');
            const data = await (api as any).get('/api/v1/integrations') as any;
            const meta: Record<string, IntegrationMeta> = {};
            for (const item of (data.integrations || [])) meta[item.type] = item;
            setListMeta(meta);
        } catch {
            setSavedMsg('Save failed — check API connection.');
        } finally {
            setSaving(false);
            setTimeout(() => setSavedMsg(''), 4000);
        }
    };

    const handleTest = async () => {
        setTesting(true);
        setTestResult(null);
        try {
            const result = await (api as any).post(`/api/v1/integrations/${selected}/test`, {}) as any;
            setTestResult({
                success: result.success === true,
                message: result.success ? JSON.stringify(result, null, 2) : (result.error || 'Test failed'),
            });
            // Refresh meta
            try {
                const data = await (api as any).get('/api/v1/integrations') as any;
                const meta: Record<string, IntegrationMeta> = {};
                for (const item of (data.integrations || [])) meta[item.type] = item;
                setListMeta(meta);
            } catch { /* ignore */ }
        } catch {
            setTestResult({ success: false, message: 'Could not reach the API to run the test.' });
        } finally {
            setTesting(false);
        }
    };

    const getStatus = (key: string): StatusType => {
        const m = listMeta[key];
        if (!m) return 'not_configured';
        if (m.last_test_status === 'failed') return 'error';
        if (m.is_configured) return 'configured';
        return 'not_configured';
    };

    const categories = [...new Set(INTEGRATIONS.map(i => i.category))];
    const selectedInteg = INTEGRATIONS.find(i => i.key === selected)!;
    const SelectedIcon = selectedInteg.icon;
    const fields = FIELD_DEFS[selected] || [];
    const selectedMeta = listMeta[selected];

    return (
        <div style={{ display: 'flex', height: 'calc(100vh - 112px)', gap: 0, borderRadius: 16, overflow: 'hidden', border: '1px solid #E2E8F0', background: '#fff' }}>
            {/* ── Sidebar ── */}
            <div style={{ width: 220, borderRight: '1px solid #E2E8F0', background: '#F8FAFC', overflowY: 'auto', flexShrink: 0 }}>
                <div style={{ padding: '16px 16px 8px', fontWeight: 800, fontSize: 15, color: '#0F172A', display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Radio size={16} color="#6366F1" />
                    Pulse
                </div>
                <div style={{ padding: '4px 8px 16px' }}>
                    {categories.map(cat => (
                        <div key={cat}>
                            <div style={{ padding: '8px 8px 4px', fontSize: 10, color: '#94A3B8', fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
                                {cat}
                            </div>
                            {INTEGRATIONS.filter(i => i.category === cat).map(integ => {
                                const Icon = integ.icon;
                                const active = selected === integ.key;
                                const st = getStatus(integ.key);
                                return (
                                    <div
                                        key={integ.key}
                                        onClick={() => setSelected(integ.key)}
                                        style={{
                                            display: 'flex', alignItems: 'center', gap: 8,
                                            padding: '8px 10px', borderRadius: 8, cursor: 'pointer',
                                            background: active ? 'rgba(99,102,241,0.08)' : 'transparent',
                                            color: active ? '#6366F1' : '#374151',
                                            fontWeight: active ? 600 : 400,
                                            justifyContent: 'space-between',
                                            transition: 'all 0.12s',
                                        }}
                                        onMouseEnter={e => { if (!active) e.currentTarget.style.background = '#EFF6FF'; }}
                                        onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent'; }}
                                    >
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                            <Icon size={14} />
                                            <span style={{ fontSize: 12 }}>{integ.label}</span>
                                        </div>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                                            <StatusDot status={st} />
                                            {active && <ChevronRight size={12} />}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    ))}
                </div>
            </div>

            {/* ── Main Panel ── */}
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflowY: 'auto' }}>
                {/* Header */}
                <div style={{ padding: '20px 28px 16px', borderBottom: '1px solid #F1F5F9' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                            <div style={{
                                width: 42, height: 42, borderRadius: 12,
                                background: 'linear-gradient(135deg, #EEF2FF, #DBEAFE)',
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                            }}>
                                <SelectedIcon size={20} color="#6366F1" />
                            </div>
                            <div>
                                <div style={{ fontSize: 17, fontWeight: 800, color: '#0F172A' }}>{selectedInteg.label}</div>
                                <div style={{ fontSize: 12, color: '#64748B', marginTop: 2, display: 'flex', alignItems: 'center', gap: 6 }}>
                                    <StatusDot status={getStatus(selected)} />
                                    {getStatus(selected) === 'configured' ? 'Connected' : getStatus(selected) === 'error' ? 'Connection Error' : 'Not configured'}
                                    {selectedMeta?.last_tested_at && (
                                        <span style={{ color: '#CBD5E1' }}>· Last tested {new Date(selectedMeta.last_tested_at).toLocaleDateString()}</span>
                                    )}
                                </div>
                            </div>
                        </div>
                        <div style={{ display: 'flex', gap: 8 }}>
                            <button
                                onClick={handleTest}
                                disabled={testing}
                                style={{
                                    display: 'flex', alignItems: 'center', gap: 6,
                                    padding: '8px 16px', borderRadius: 8,
                                    background: '#F8FAFC', border: '1px solid #E2E8F0',
                                    cursor: testing ? 'not-allowed' : 'pointer', fontSize: 12, fontWeight: 600, color: '#374151',
                                    opacity: testing ? 0.7 : 1,
                                }}
                            >
                                <RefreshCw size={13} style={{ animation: testing ? 'spin 1s linear infinite' : 'none' }} />
                                {testing ? 'Testing…' : 'Test Connection'}
                            </button>
                            <button
                                onClick={handleSave}
                                disabled={saving}
                                style={{
                                    display: 'flex', alignItems: 'center', gap: 6,
                                    padding: '8px 16px', borderRadius: 8,
                                    background: 'linear-gradient(135deg, #6366F1, #3B82F6)',
                                    border: 'none', cursor: saving ? 'not-allowed' : 'pointer',
                                    fontSize: 12, fontWeight: 700, color: '#fff',
                                    opacity: saving ? 0.7 : 1,
                                    boxShadow: '0 4px 12px rgba(99,102,241,0.3)',
                                }}
                            >
                                <Save size={13} />
                                {saving ? 'Saving…' : 'Save'}
                            </button>
                        </div>
                    </div>
                    {savedMsg && (
                        <div style={{ marginTop: 8, fontSize: 12, color: savedMsg.includes('fail') ? '#EF4444' : '#10B981', fontWeight: 600 }}>
                            {savedMsg}
                        </div>
                    )}
                </div>

                {/* Form */}
                <div style={{ padding: '24px 28px', flex: 1 }}>
                    {/* Test result */}
                    {testResult && (
                        <div style={{
                            marginBottom: 20, padding: '14px 16px', borderRadius: 10,
                            background: testResult.success ? '#ECFDF5' : '#FEF2F2',
                            border: `1px solid ${testResult.success ? '#A7F3D0' : '#FECACA'}`,
                        }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                                {testResult.success
                                    ? <CheckCircle size={14} color="#10B981" />
                                    : <AlertTriangle size={14} color="#EF4444" />}
                                <span style={{ fontWeight: 700, fontSize: 13, color: testResult.success ? '#059669' : '#DC2626' }}>
                                    {testResult.success ? 'Connection successful' : 'Connection failed'}
                                </span>
                            </div>
                            <pre style={{ margin: 0, fontSize: 11, color: '#374151', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                                {testResult.message}
                            </pre>
                        </div>
                    )}

                    {/* Fields */}
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px 24px' }}>
                        {fields.map(field => (
                            <div key={field.key} style={{ gridColumn: field.type === 'textarea' ? '1 / -1' : 'auto' }}>
                                <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 6 }}>
                                    {field.label}
                                    {field.hint && <span style={{ fontWeight: 400, color: '#94A3B8', marginLeft: 6 }}>({field.hint})</span>}
                                </label>
                                {field.type === 'textarea' ? (
                                    <textarea
                                        value={formData[field.key] || ''}
                                        onChange={e => setFormData(d => ({ ...d, [field.key]: e.target.value }))}
                                        placeholder={field.placeholder}
                                        rows={5}
                                        style={{
                                            width: '100%', padding: '10px 12px', borderRadius: 8,
                                            border: '1px solid #E2E8F0', fontSize: 12, fontFamily: 'monospace',
                                            outline: 'none', resize: 'vertical',
                                            background: '#F8FAFC', boxSizing: 'border-box',
                                        }}
                                        onFocus={e => (e.target.style.border = '1px solid #6366F1')}
                                        onBlur={e => (e.target.style.border = '1px solid #E2E8F0')}
                                    />
                                ) : (
                                    <input
                                        type={field.type === 'password' ? 'password' : 'text'}
                                        value={formData[field.key] || ''}
                                        onChange={e => setFormData(d => ({ ...d, [field.key]: e.target.value }))}
                                        placeholder={field.placeholder}
                                        style={{
                                            width: '100%', padding: '10px 12px', borderRadius: 8,
                                            border: '1px solid #E2E8F0', fontSize: 12,
                                            outline: 'none', background: '#F8FAFC', boxSizing: 'border-box',
                                            fontFamily: field.type === 'password' ? 'password' : 'inherit',
                                        }}
                                        onFocus={e => (e.target.style.border = '1px solid #6366F1')}
                                        onBlur={e => (e.target.style.border = '1px solid #E2E8F0')}
                                    />
                                )}
                            </div>
                        ))}
                    </div>

                    {/* Info box */}
                    <div style={{ marginTop: 24, padding: '14px 16px', borderRadius: 10, background: '#F8FAFC', border: '1px solid #E2E8F0' }}>
                        <div style={{ fontSize: 12, color: '#64748B', lineHeight: 1.6 }}>
                            <strong style={{ color: '#374151' }}>🔒 Security:</strong> All credentials are encrypted at rest using AES-256 (Fernet). They are never logged and are masked when retrieved.
                            <br />
                            <strong style={{ color: '#374151' }}>📋 Scope:</strong> Click <em>Test Connection</em> to verify credentials are valid before saving.
                        </div>
                    </div>
                </div>
            </div>

            <style>{`
                @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
            `}</style>
        </div>
    );
}
