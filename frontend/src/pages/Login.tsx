// frontend/src/pages/Login.tsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Zap, Lock, Mail, AlertCircle, Eye, EyeOff } from 'lucide-react';
import api from '../services/api';

export default function Login() {
    const navigate = useNavigate();
    const [email, setEmail] = useState('admin@neuralops.io');
    const [password, setPassword] = useState('');
    const [showPass, setShowPass] = useState(false);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setLoading(true);
        try {
            await api.login(email, password);
            navigate('/');
        } catch {
            setError('Invalid email or password. Try admin@neuralops.io / Admin@123');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={{
            minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'linear-gradient(135deg, #F0F4FF 0%, #FFFFFF 50%, #F8FAFC 100%)',
            position: 'relative',
        }}>
            {/* Subtle background pattern */}
            <div style={{
                position: 'fixed', inset: 0, opacity: 0.4,
                backgroundImage: 'radial-gradient(circle at 1px 1px, #E2E8F0 1px, transparent 0)',
                backgroundSize: '32px 32px', pointerEvents: 'none',
            }} />

            {/* Accent blobs */}
            <div style={{ position: 'fixed', top: -150, right: -100, width: 500, height: 500, borderRadius: '50%', background: 'radial-gradient(circle, rgba(99,102,241,0.06) 0%, transparent 70%)', pointerEvents: 'none' }} />
            <div style={{ position: 'fixed', bottom: -150, left: -100, width: 400, height: 400, borderRadius: '50%', background: 'radial-gradient(circle, rgba(59,130,246,0.05) 0%, transparent 70%)', pointerEvents: 'none' }} />

            <div style={{ width: 420, display: 'flex', flexDirection: 'column', gap: 32, position: 'relative', zIndex: 1 }}>
                {/* Logo & brand */}
                <div style={{ textAlign: 'center' }}>
                    <div style={{
                        width: 68, height: 68, borderRadius: 20, margin: '0 auto 20px',
                        background: 'linear-gradient(135deg, #6366F1, #3B82F6)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        boxShadow: '0 12px 32px rgba(99,102,241,0.35)',
                    }}>
                        <Zap size={30} color="#fff" strokeWidth={2.5} />
                    </div>
                    <h1 style={{ fontSize: 30, fontWeight: 800, color: '#0F172A', letterSpacing: '-0.03em' }}>PulseQ</h1>
                    <p style={{ fontSize: 14, color: '#64748B', marginTop: 8 }}>AI DevOps Intelligence Platform</p>
                </div>

                {/* Card */}
                <div style={{
                    background: '#FFFFFF', border: '1px solid #E2E8F0',
                    borderRadius: 20, padding: 36,
                    boxShadow: '0 8px 40px rgba(0,0,0,0.07), 0 1px 3px rgba(0,0,0,0.04)',
                }}>
                    <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 6, color: '#0F172A' }}>Welcome back</h2>
                    <p style={{ fontSize: 13, color: '#64748B', marginBottom: 28 }}>Sign in to your account to continue</p>

                    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
                        {/* Email */}
                        <div>
                            <label style={{ fontSize: 12, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 6 }}>
                                EMAIL ADDRESS
                            </label>
                            <div style={{ position: 'relative' }}>
                                <Mail size={15} style={{ position: 'absolute', left: 13, top: '50%', transform: 'translateY(-50%)', color: '#94A3B8' }} />
                                <input
                                    type="text" required value={email}
                                    onChange={e => setEmail(e.target.value)}
                                    placeholder="admin@neuralops.io"
                                    style={{
                                        width: '100%', background: '#F8FAFC',
                                        border: '1px solid #E2E8F0', borderRadius: 10,
                                        padding: '11px 12px 11px 40px',
                                        color: '#0F172A', fontSize: 13.5, outline: 'none',
                                        boxSizing: 'border-box', transition: 'all 0.15s',
                                    }}
                                    onFocus={e => { e.target.style.borderColor = '#6366F1'; e.target.style.boxShadow = '0 0 0 3px rgba(99,102,241,0.12)'; e.target.style.background = '#FFFFFF'; }}
                                    onBlur={e => { e.target.style.borderColor = '#E2E8F0'; e.target.style.boxShadow = 'none'; e.target.style.background = '#F8FAFC'; }}
                                />
                            </div>
                        </div>

                        {/* Password */}
                        <div>
                            <label style={{ fontSize: 12, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 6 }}>
                                PASSWORD
                            </label>
                            <div style={{ position: 'relative' }}>
                                <Lock size={15} style={{ position: 'absolute', left: 13, top: '50%', transform: 'translateY(-50%)', color: '#94A3B8' }} />
                                <input
                                    type={showPass ? 'text' : 'password'} required value={password}
                                    onChange={e => setPassword(e.target.value)}
                                    placeholder="Enter your password"
                                    style={{
                                        width: '100%', background: '#F8FAFC',
                                        border: '1px solid #E2E8F0', borderRadius: 10,
                                        padding: '11px 42px 11px 40px',
                                        color: '#0F172A', fontSize: 13.5, outline: 'none',
                                        boxSizing: 'border-box', transition: 'all 0.15s',
                                    }}
                                    onFocus={e => { e.target.style.borderColor = '#6366F1'; e.target.style.boxShadow = '0 0 0 3px rgba(99,102,241,0.12)'; e.target.style.background = '#FFFFFF'; }}
                                    onBlur={e => { e.target.style.borderColor = '#E2E8F0'; e.target.style.boxShadow = 'none'; e.target.style.background = '#F8FAFC'; }}
                                />
                                <button type="button" onClick={() => setShowPass(s => !s)} style={{
                                    position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)',
                                    background: 'none', border: 'none', cursor: 'pointer', color: '#94A3B8', padding: 2,
                                }}>
                                    {showPass ? <EyeOff size={15} /> : <Eye size={15} />}
                                </button>
                            </div>
                        </div>

                        {/* Error */}
                        {error && (
                            <div style={{
                                display: 'flex', gap: 8, alignItems: 'flex-start',
                                color: '#DC2626', fontSize: 12.5, padding: '10px 14px',
                                background: '#FEF2F2', borderRadius: 8, border: '1px solid #FECACA',
                            }}>
                                <AlertCircle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
                                <span>{error}</span>
                            </div>
                        )}

                        {/* Submit */}
                        <button type="submit" disabled={loading || !email || !password} style={{
                            width: '100%', padding: '12px', background: 'linear-gradient(135deg, #6366F1, #4F46E5)',
                            color: '#fff', border: 'none', borderRadius: 10, fontSize: 14, fontWeight: 600,
                            cursor: loading ? 'not-allowed' : 'pointer', opacity: loading ? 0.7 : 1,
                            transition: 'all 0.15s', marginTop: 4,
                            boxShadow: '0 4px 14px rgba(99,102,241,0.35)',
                        }}>
                            {loading ? 'Signing in…' : 'Sign In →'}
                        </button>
                    </form>

                    {/* Default credentials hint */}
                    <div style={{ marginTop: 20, padding: 12, background: '#F0F4FF', borderRadius: 8, border: '1px solid #C7D2FE' }}>
                        <div style={{ fontSize: 11.5, color: '#4F46E5', fontWeight: 600, marginBottom: 4 }}>Default Credentials</div>
                        <div style={{ fontSize: 11.5, color: '#6366F1', fontFamily: 'monospace' }}>
                            admin@neuralops.io / Admin@123
                        </div>
                        <div style={{ fontSize: 11, color: '#64748B', marginTop: 4 }}>
                            Also works: admin / admin123
                        </div>
                    </div>
                </div>

                <div style={{ textAlign: 'center', fontSize: 12, color: '#94A3B8' }}>
                    Powered by Gemini 1.5 Flash · PulseQ AI SRE Platform
                </div>
            </div>
        </div>
    );
}
