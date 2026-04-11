/**
 * Developer.tsx — AI Developer Mode
 *
 * Flow:
 *   1. No repo selected → beautiful repository picker
 *   2. Repo selected → 3-pane IDE view:
 *        Left:   folder tree (real data from analysis)
 *        Middle: language + stats overview + Recent logs
 *        Right:  Curated placeholder improvement suggestions (language-aware)
 *
 * NO auto LLM analysis. Zero waiting. Instant insight.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
    Code2, ChevronRight, ChevronDown, GitBranch, Globe,
    FileText, AlertTriangle, Activity, ExternalLink,
    FolderOpen, Folder, ArrowRight, Sparkles, Zap,
    Shield, Eye, Brain, Cpu, RefreshCw, Loader2,
    Clock, Search
} from 'lucide-react';
import api from '../services/api';

// ─────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────
interface Repo {
    id: string;
    name: string;
    owner?: string;
    repo_url?: string;
    primary_language?: string;
    language?: string;
    status?: string;
    description?: string;
    stars?: number;
    open_issues?: number;
}

interface TreeNode {
    path: string;
    name: string;
    type: 'file' | 'dir';
    children?: TreeNode[];
}

// ─────────────────────────────────────────────────────────────
// Language-aware placeholder suggestions
// ─────────────────────────────────────────────────────────────
interface Hint {
    id: string;
    category: 'performance' | 'security' | 'readability' | 'best_practice' | 'error_handling' | 'memory';
    priority: 'high' | 'medium' | 'low';
    title: string;
    before: string;
    after: string;
    explanation: string;
}

const LANGUAGE_HINTS: Record<string, Hint[]> = {
    python: [
        {
            id: 'py-1', category: 'performance', priority: 'high',
            title: 'Use list comprehension instead of for-loop append',
            before: `result = []\nfor item in data:\n    if item > 0:\n        result.append(item * 2)`,
            after: `result = [item * 2 for item in data if item > 0]`,
            explanation: 'List comprehensions are 30–50% faster than equivalent for-loop constructs and significantly more readable.',
        },
        {
            id: 'py-2', category: 'error_handling', priority: 'high',
            title: 'Catch specific exceptions instead of bare except',
            before: `try:\n    result = risky_operation()\nexcept:\n    pass`,
            after: `try:\n    result = risky_operation()\nexcept ValueError as e:\n    logger.error("Validation failed", exc_info=e)\nexcept Exception as e:\n    raise`,
            explanation: 'Bare except silently swallows all errors including KeyboardInterrupt and SystemExit. Always catch specific exception types.',
        },
        {
            id: 'py-3', category: 'readability', priority: 'medium',
            title: 'Add type hints to function signatures',
            before: `def process(data, threshold):\n    return [x for x in data if x > threshold]`,
            after: `def process(data: list[float], threshold: float) -> list[float]:\n    return [x for x in data if x > threshold]`,
            explanation: 'Type hints enable IDE auto-complete, catch bugs at development time, and serve as inline documentation.',
        },
        {
            id: 'py-4', category: 'memory', priority: 'medium',
            title: 'Use generators instead of building full lists',
            before: `def read_lines(file_path):\n    with open(file_path) as f:\n        return f.readlines()`,
            after: `def read_lines(file_path):\n    with open(file_path) as f:\n        yield from f`,
            explanation: 'Generators process data lazily, using O(1) memory instead of O(n) for large files or datasets.',
        },
        {
            id: 'py-5', category: 'security', priority: 'high',
            title: 'Never store secrets in source code',
            before: `DB_PASSWORD = "supersecret123"\nAPI_KEY = "sk-abc123xyz"`,
            after: `import os\nDB_PASSWORD = os.environ.get("DB_PASSWORD")\nAPI_KEY = os.environ.get("API_KEY")`,
            explanation: 'Hardcoded credentials are exposed in version control. Always use environment variables or a secrets manager.',
        },
        {
            id: 'py-6', category: 'best_practice', priority: 'low',
            title: 'Use pathlib instead of os.path for file operations',
            before: `import os\nfull_path = os.path.join(base_dir, "data", "file.csv")`,
            after: `from pathlib import Path\nfull_path = Path(base_dir) / "data" / "file.csv"`,
            explanation: 'pathlib provides an object-oriented interface that is more readable and cross-platform.',
        },
    ],
    javascript: [
        {
            id: 'js-1', category: 'performance', priority: 'high',
            title: 'Debounce expensive event handlers',
            before: `input.addEventListener('keyup', (e) => {\n  fetch('/api/search?q=' + e.target.value);\n});`,
            after: `const debounce = (fn, ms) => {\n  let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };\n};\ninput.addEventListener('keyup', debounce((e) => {\n  fetch('/api/search?q=' + e.target.value);\n}, 300));`,
            explanation: 'Without debouncing, every keystroke fires an API call. Debouncing waits 300ms of inactivity, reducing requests by 10x.',
        },
        {
            id: 'js-2', category: 'error_handling', priority: 'high',
            title: 'Always handle Promise rejections',
            before: `async function loadUser(id) {\n  const res = await fetch('/api/users/' + id);\n  return res.json();\n}`,
            after: `async function loadUser(id) {\n  const res = await fetch('/api/users/' + id);\n  if (!res.ok) throw new Error(\`HTTP \${res.status}\`);\n  return res.json();\n}`,
            explanation: 'fetch() does not reject on HTTP error status codes. Always check res.ok before calling .json().',
        },
        {
            id: 'js-3', category: 'security', priority: 'high',
            title: 'Sanitize user input before rendering innerHTML',
            before: `div.innerHTML = userComment;`,
            after: `div.textContent = userComment;\n// Or use DOMPurify for rich HTML:\n// div.innerHTML = DOMPurify.sanitize(userComment);`,
            explanation: 'Setting innerHTML with user-provided data enables XSS attacks. Use textContent or a sanitization library.',
        },
        {
            id: 'js-4', category: 'readability', priority: 'medium',
            title: 'Use optional chaining instead of nested null checks',
            before: `const city = user && user.address && user.address.city;`,
            after: `const city = user?.address?.city;`,
            explanation: 'Optional chaining (?.) is cleaner, shorter, and handles null/undefined gracefully without verbose conditionals.',
        },
        {
            id: 'js-5', category: 'memory', priority: 'medium',
            title: 'Remove event listeners when no longer needed',
            before: `button.addEventListener('click', handler);\n// Element removed from DOM — listener still lives in memory`,
            after: `const controller = new AbortController();\nbutton.addEventListener('click', handler, { signal: controller.signal });\n// Later:\ncontroller.abort(); // Removes listener automatically`,
            explanation: 'Orphaned event listeners keep references to DOM elements, causing memory leaks in SPAs.',
        },
        {
            id: 'js-6', category: 'best_practice', priority: 'low',
            title: 'Use const and let instead of var',
            before: `var count = 0;\nvar name = "Alice";`,
            after: `let count = 0;\nconst name = "Alice";`,
            explanation: 'var is function-scoped and hoisted, causing unexpected behavior. const/let are block-scoped and intention-revealing.',
        },
    ],
    typescript: [
        {
            id: 'ts-1', category: 'best_practice', priority: 'high',
            title: 'Avoid the any type — use unknown for safe typing',
            before: `function parseData(raw: any) {\n  return raw.value.trim();\n}`,
            after: `function parseData(raw: unknown): string {\n  if (typeof raw !== 'object' || raw === null) throw new Error('Invalid data');\n  const { value } = raw as { value: string };\n  return value.trim();\n}`,
            explanation: 'any disables TypeScript\'s safety net entirely. unknown forces you to validate before accessing properties.',
        },
        {
            id: 'ts-2', category: 'readability', priority: 'medium',
            title: 'Use discriminated unions for exhaustive checks',
            before: `type Shape = { type: string; radius?: number; width?: number; }`,
            after: `type Circle = { type: 'circle'; radius: number; }\ntype Square = { type: 'square'; width: number; }\ntype Shape = Circle | Square;`,
            explanation: 'Discriminated unions let TypeScript verify exhaustive switch/if coverage at compile time, preventing runtime errors.',
        },
        {
            id: 'ts-3', category: 'error_handling', priority: 'high',
            title: 'Type your async function return values',
            before: `async function fetchUser(id: string) {\n  const r = await fetch(\`/users/\${id}\`);\n  return r.json();\n}`,
            after: `interface User { id: string; name: string; email: string; }\nasync function fetchUser(id: string): Promise<User> {\n  const r = await fetch(\`/users/\${id}\`);\n  if (!r.ok) throw new Error(\`User \${id} not found\`);\n  return r.json() as Promise<User>;\n}`,
            explanation: 'Explicit return types make API contracts clear and catch mistakes when the API shape changes.',
        },
        {
            id: 'ts-4', category: 'performance', priority: 'medium',
            title: 'Use Record<K,V> instead of index signatures',
            before: `interface Config { [key: string]: string; }`,
            after: `type Config = Record<string, string>;`,
            explanation: 'Record<K,V> is more concise and communicates intent more clearly than raw index signatures.',
        },
    ],
    java: [
        {
            id: 'java-1', category: 'performance', priority: 'high',
            title: 'Use StringBuilder for string concatenation in loops',
            before: `String result = "";\nfor (String s : list) {\n    result += s + ", ";\n}`,
            after: `StringBuilder sb = new StringBuilder();\nfor (String s : list) {\n    sb.append(s).append(", ");\n}\nString result = sb.toString();`,
            explanation: 'String concatenation in a loop creates a new String object each iteration. StringBuilder is O(n) vs O(n²).',
        },
        {
            id: 'java-2', category: 'error_handling', priority: 'high',
            title: 'Use try-with-resources for AutoCloseable objects',
            before: `Connection conn = null;\ntry {\n    conn = getConnection();\n    // use conn\n} finally {\n    if (conn != null) conn.close();\n}`,
            after: `try (Connection conn = getConnection()) {\n    // use conn\n}  // auto-closed — even on exception`,
            explanation: 'try-with-resources guarantees cleanup even when exceptions occur and eliminates boilerplate finally blocks.',
        },
        {
            id: 'java-3', category: 'readability', priority: 'medium',
            title: 'Use Optional to avoid NullPointerException',
            before: `User user = findUser(id);\nif (user != null) {\n    return user.getEmail();\n}\nreturn "unknown";`,
            after: `return findUser(id)\n    .map(User::getEmail)\n    .orElse("unknown");`,
            explanation: 'Optional makes null-handling explicit, chainable, and eliminates verbose null checks.',
        },
    ],
    go: [
        {
            id: 'go-1', category: 'error_handling', priority: 'high',
            title: 'Always handle returned errors explicitly',
            before: `data, _ := ioutil.ReadFile("config.json")`,
            after: `data, err := ioutil.ReadFile("config.json")\nif err != nil {\n    return fmt.Errorf("reading config: %w", err)\n}`,
            explanation: 'Ignoring errors with _ is a common Go anti-pattern. Wrapped errors provide useful stack context.',
        },
        {
            id: 'go-2', category: 'performance', priority: 'high',
            title: 'Pre-allocate slices when length is known',
            before: `var result []int\nfor _, v := range data {\n    result = append(result, v*2)\n}`,
            after: `result := make([]int, 0, len(data))\nfor _, v := range data {\n    result = append(result, v*2)\n}`,
            explanation: 'Pre-allocating prevents repeated re-allocation and copying as the slice grows beyond capacity.',
        },
        {
            id: 'go-3', category: 'best_practice', priority: 'medium',
            title: 'Use context for cancellation and timeouts',
            before: `resp, err := http.Get(url)`,
            after: `ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)\ndefer cancel()\nreq, _ := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)\nresp, err := http.DefaultClient.Do(req)`,
            explanation: 'context propagates cancellation signals through goroutines and enforces timeouts on blocking calls.',
        },
    ],
    default: [
        {
            id: 'def-1', category: 'security', priority: 'high',
            title: 'Remove hardcoded credentials from source code',
            before: `const PASSWORD = "admin123";\nconst API_KEY = "secret-key-xyz";`,
            after: `const PASSWORD = process.env.DB_PASSWORD;\nconst API_KEY = process.env.API_KEY;`,
            explanation: 'Credentials in source code are exposed to anyone with repository access. Use environment variables or a vault.',
        },
        {
            id: 'def-2', category: 'best_practice', priority: 'medium',
            title: 'Add input validation at every entry point',
            before: `function saveUser(data) {\n    db.insert(data);  // No validation\n}`,
            after: `function saveUser(data) {\n    if (!data?.email || !data?.name) {\n        throw new Error("email and name are required");\n    }\n    db.insert(data);\n}`,
            explanation: 'Validating inputs at boundaries prevents data corruption and improves error messages for users.',
        },
        {
            id: 'def-3', category: 'readability', priority: 'low',
            title: 'Extract magic numbers into named constants',
            before: `if (score > 8.5) { badge = "gold"; }\nsetTimeout(refresh, 86400000);`,
            after: `const GOLD_THRESHOLD = 8.5;\nconst ONE_DAY_MS = 24 * 60 * 60 * 1000;\nif (score > GOLD_THRESHOLD) { badge = "gold"; }\nsetTimeout(refresh, ONE_DAY_MS);`,
            explanation: 'Named constants communicate intent, allow centralized updates, and eliminate guesswork for future maintainers.',
        },
    ],
};

function getHints(language?: string): Hint[] {
    if (!language) return LANGUAGE_HINTS.default;
    const key = language.toLowerCase();
    return LANGUAGE_HINTS[key] || LANGUAGE_HINTS.default;
}

// ─────────────────────────────────────────────────────────────
// Category & Priority config
// ─────────────────────────────────────────────────────────────
const CAT: Record<string, { icon: React.ReactNode; color: string; bg: string }> = {
    performance: { icon: <Zap size={12} />, color: '#F97316', bg: '#FFF7ED' },
    security: { icon: <Shield size={12} />, color: '#EF4444', bg: '#FFF5F5' },
    readability: { icon: <Eye size={12} />, color: '#3B82F6', bg: '#EFF6FF' },
    best_practice: { icon: <Code2 size={12} />, color: '#10B981', bg: '#F0FDF4' },
    error_handling: { icon: <AlertTriangle size={12} />, color: '#EAB308', bg: '#FEFCE8' },
    memory: { icon: <Cpu size={12} />, color: '#8B5CF6', bg: '#F5F3FF' },
};
const PRI: Record<string, { color: string; bg: string; label: string }> = {
    high: { color: '#DC2626', bg: '#FEE2E2', label: 'High' },
    medium: { color: '#CA8A04', bg: '#FEF9C3', label: 'Medium' },
    low: { color: '#2563EB', bg: '#DBEAFE', label: 'Low' },
};
const LANG_COLORS: Record<string, string> = {
    python: '#3776AB', javascript: '#F7DF1E', typescript: '#3178C6',
    java: '#ED8B00', go: '#00ADD8', rust: '#DEA584', cpp: '#00599C',
    c: '#A8B9CC', ruby: '#701516', php: '#777BB4', default: '#6366F1',
};



// ─────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────

function TreeNodeView({ node, depth = 0 }: { node: TreeNode; depth?: number }) {
    const [open, setOpen] = useState(depth < 2);
    const isDir = node.type === 'dir';
    const indent = depth * 16;
    return (
        <div>
            <button
                onClick={() => isDir && setOpen(o => !o)}
                style={{
                    width: '100%', border: 'none', background: 'none', textAlign: 'left',
                    display: 'flex', alignItems: 'center', gap: 5,
                    padding: `4px 8px 4px ${8 + indent}px`,
                    cursor: isDir ? 'pointer' : 'default',
                    borderRadius: 5,
                    color: isDir ? '#94A3B8' : '#64748B',
                }}
            >
                {isDir ? (
                    open ? <ChevronDown size={12} /> : <ChevronRight size={12} />
                ) : <span style={{ width: 12 }} />}
                {isDir
                    ? <Folder size={13} color={open ? '#FBBF24' : '#94A3B8'} />
                    : <FileText size={12} color="#64748B" />}
                <span style={{ fontSize: 12, fontFamily: 'monospace', color: isDir ? '#C7D2FE' : '#94A3B8' }}>
                    {node.name}
                </span>
            </button>
            {isDir && open && node.children?.map(child => (
                <TreeNodeView key={child.path} node={child} depth={depth + 1} />
            ))}
        </div>
    );
}

function buildTree(paths: string[]): TreeNode[] {
    const root: Record<string, any> = {};
    for (const p of paths) {
        const parts = p.split('/');
        let cur = root;
        for (let i = 0; i < parts.length; i++) {
            const part = parts[i];
            if (!cur[part]) cur[part] = i === parts.length - 1 ? null : {};
            if (cur[part] !== null) cur = cur[part];
        }
    }
    function toNodes(obj: Record<string, any>, prefix = ''): TreeNode[] {
        return Object.entries(obj)
            .map(([name, children]) => ({
                path: prefix ? `${prefix}/${name}` : name,
                name,
                type: (children === null ? 'file' : 'dir') as 'file' | 'dir',
                children: children ? toNodes(children, prefix ? `${prefix}/${name}` : name) : undefined,
            }))
            .sort((a, b) => {
                if (a.type !== b.type) return a.type === 'dir' ? -1 : 1;
                return a.name.localeCompare(b.name);
            });
    }
    return toNodes(root);
}

function HintCard({ hint, expanded, onToggle }: { hint: Hint; expanded: boolean; onToggle: () => void }) {
    const cat = CAT[hint.category] || CAT.best_practice;
    const pri = PRI[hint.priority] || PRI.low;
    const [view, setView] = useState<'before' | 'after'>('before');
    return (
        <div
            style={{
                background: '#fff', border: '1px solid #E2E8F0',
                borderLeft: `3px solid ${cat.color}`,
                borderRadius: 10, overflow: 'hidden', marginBottom: 10,
                transition: 'box-shadow 0.15s',
                boxShadow: expanded ? '0 4px 16px rgba(0,0,0,0.07)' : 'none',
            }}
        >
            {/* Header */}
            <button
                onClick={onToggle}
                style={{
                    width: '100%', border: 'none', background: 'none', cursor: 'pointer',
                    padding: '11px 14px', textAlign: 'left', display: 'flex', alignItems: 'flex-start', gap: 10,
                }}
            >
                <div style={{ display: 'flex', alignItems: 'center', gap: 5, flexShrink: 0, marginTop: 1 }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, fontWeight: 700, color: cat.color, background: cat.bg, padding: '2px 7px', borderRadius: 20 }}>
                        {cat.icon} {hint.category.replace('_', ' ')}
                    </span>
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: '#0F172A', lineHeight: 1.4, marginBottom: 3 }}>
                        {hint.title}
                    </div>
                    <div style={{ fontSize: 11, color: '#64748B', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {hint.explanation.slice(0, 80)}…
                    </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                    <span style={{ fontSize: 10, fontWeight: 700, color: pri.color, background: pri.bg, padding: '2px 7px', borderRadius: 20 }}>
                        {pri.label}
                    </span>
                    {expanded ? <ChevronDown size={14} color="#94A3B8" /> : <ChevronRight size={14} color="#94A3B8" />}
                </div>
            </button>

            {expanded && (
                <div style={{ borderTop: '1px solid #F1F5F9', padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 12, background: '#FAFBFF' }}>
                    <p style={{ margin: 0, fontSize: 13, color: '#374151', lineHeight: 1.7 }}>{hint.explanation}</p>
                    {/* Toggle before/after */}
                    <div>
                        <div style={{ display: 'flex', marginBottom: 8 }}>
                            {(['before', 'after'] as const).map(v => (
                                <button
                                    key={v}
                                    onClick={() => setView(v)}
                                    style={{
                                        padding: '4px 14px', fontSize: 11, fontWeight: 700, border: 'none', cursor: 'pointer',
                                        background: view === v ? (v === 'before' ? '#FEE2E2' : '#DCFCE7') : '#F1F5F9',
                                        color: view === v ? (v === 'before' ? '#DC2626' : '#059669') : '#94A3B8',
                                        borderRadius: v === 'before' ? '8px 0 0 8px' : '0 8px 8px 0',
                                        transition: 'all 0.15s',
                                    }}
                                >
                                    {v === 'before' ? '● Current code' : '● Improved'}
                                </button>
                            ))}
                        </div>
                        <div
                            style={{
                                background: view === 'before' ? '#FFF7F7' : '#F0FDF4',
                                border: `1px solid ${view === 'before' ? '#FECACA' : '#BBF7D0'}`,
                                borderRadius: 8, overflow: 'hidden',
                            }}
                        >
                            <div style={{
                                padding: '5px 14px', fontSize: 10, fontWeight: 700,
                                color: view === 'before' ? '#DC2626' : '#059669',
                                background: view === 'before' ? '#FEE2E2' : '#DCFCE7',
                                display: 'flex', alignItems: 'center', gap: 5,
                            }}>
                                <ArrowRight size={10} />
                                {view === 'before' ? 'Current approach' : 'Better approach'}
                            </div>
                            <pre style={{
                                margin: 0, padding: '12px 14px', fontSize: 12, lineHeight: 1.6,
                                fontFamily: "'Fira Code', 'Cascadia Code', monospace",
                                color: '#1E293B', overflowX: 'auto',
                                background: 'transparent',
                            }}>
                                {view === 'before' ? hint.before : hint.after}
                            </pre>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

// ─────────────────────────────────────────────────────────────
// Repo Picker — shown when no repo is selected
// ─────────────────────────────────────────────────────────────
function RepoPicker({ repos, loading, onSelect }: {
    repos: Repo[];
    loading: boolean;
    onSelect: (repo: Repo) => void;
}) {
    const [search, setSearch] = useState('');
    const filtered = repos.filter(r =>
        `${r.name} ${r.owner} ${r.description}`.toLowerCase().includes(search.toLowerCase())
    );
    const langColor = (lang?: string) => LANG_COLORS[lang?.toLowerCase() || ''] || LANG_COLORS.default;

    return (
        <div style={{ minHeight: '100vh', background: '#F8FAFC', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-start', padding: '48px 24px' }}>
            {/* Hero */}
            <div style={{ textAlign: 'center', marginBottom: 40 }}>
                <div style={{
                    width: 72, height: 72,
                    background: 'linear-gradient(135deg, #6366F1, #4F46E5)',
                    borderRadius: 20, display: 'flex', alignItems: 'center', justifyContent: 'center',
                    margin: '0 auto 20px',
                    boxShadow: '0 8px 32px rgba(99,102,241,0.3)',
                }}>
                    <Code2 size={34} color="#fff" />
                </div>
                <h1 style={{ fontSize: 28, fontWeight: 800, color: '#0F172A', margin: '0 0 10px', letterSpacing: '-0.5px' }}>
                    Developer Mode
                </h1>
                <p style={{ fontSize: 15, color: '#64748B', margin: 0 }}>
                    Choose a repository to explore its structure, language breakdown, and AI-powered improvement suggestions.
                </p>
            </div>

            {/* Search box */}
            <div style={{ width: '100%', maxWidth: 640, marginBottom: 20, position: 'relative' }}>
                <Search size={16} color="#94A3B8" style={{ position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }} />
                <input
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    placeholder="Search repositories…"
                    style={{
                        width: '100%', boxSizing: 'border-box',
                        padding: '11px 16px 11px 42px',
                        fontSize: 14, border: '1px solid #E2E8F0', borderRadius: 12,
                        background: '#fff', outline: 'none', color: '#0F172A',
                        boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
                    }}
                />
            </div>

            {/* Repo cards */}
            <div style={{ width: '100%', maxWidth: 640 }}>
                {loading ? (
                    <div style={{ textAlign: 'center', padding: 48, color: '#94A3B8' }}>
                        <Loader2 size={24} style={{ animation: 'spin 1s linear infinite', marginBottom: 12 }} />
                        <div style={{ fontSize: 14 }}>Loading repositories…</div>
                        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
                    </div>
                ) : filtered.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: 48 }}>
                        <div style={{ fontSize: 14, color: '#94A3B8' }}>No repositories found</div>
                    </div>
                ) : (
                    filtered.map(repo => {
                        const lang = repo.primary_language || repo.language;
                        const lc = langColor(lang);
                        return (
                            <button
                                key={repo.id}
                                onClick={() => onSelect(repo)}
                                style={{
                                    width: '100%', marginBottom: 10, border: '1px solid #E2E8F0',
                                    borderRadius: 14, background: '#fff', cursor: 'pointer', textAlign: 'left',
                                    padding: '16px 20px', transition: 'all 0.15s',
                                    display: 'flex', alignItems: 'center', gap: 16,
                                    boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
                                }}
                                onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = '#6366F1'; (e.currentTarget as HTMLButtonElement).style.boxShadow = '0 4px 16px rgba(99,102,241,0.12)'; }}
                                onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = '#E2E8F0'; (e.currentTarget as HTMLButtonElement).style.boxShadow = '0 1px 4px rgba(0,0,0,0.04)'; }}
                            >
                                {/* Language dot */}
                                <div style={{ width: 44, height: 44, borderRadius: 12, background: `${lc}20`, border: `2px solid ${lc}40`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                                    <Code2 size={20} color={lc} />
                                </div>

                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
                                        <span style={{ fontSize: 14, fontWeight: 700, color: '#0F172A', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                            {repo.owner ? `${repo.owner}/` : ''}{repo.name}
                                        </span>
                                        {lang && (
                                            <span style={{ fontSize: 10, fontWeight: 700, color: lc, background: `${lc}15`, padding: '2px 8px', borderRadius: 20, flexShrink: 0 }}>
                                                {lang}
                                            </span>
                                        )}
                                        <span style={{ fontSize: 10, color: repo.status === 'connected' ? '#10B981' : '#94A3B8', background: repo.status === 'connected' ? '#DCFCE7' : '#F1F5F9', padding: '2px 8px', borderRadius: 20, flexShrink: 0 }}>
                                            {repo.status || 'connected'}
                                        </span>
                                    </div>
                                    {repo.description && (
                                        <div style={{ fontSize: 12, color: '#64748B', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                            {repo.description}
                                        </div>
                                    )}
                                </div>

                                <ArrowRight size={16} color="#94A3B8" style={{ flexShrink: 0 }} />
                            </button>
                        );
                    })
                )}
            </div>
        </div>
    );
}

// ─────────────────────────────────────────────────────────────
// Main Developer component
// ─────────────────────────────────────────────────────────────
export default function Developer() {
    const [repos, setRepos] = useState<Repo[]>([]);
    const [reposLoading, setReposLoading] = useState(true);
    const [selectedRepo, setSelectedRepo] = useState<Repo | null>(null);

    // Developer view state
    const [analysis, setAnalysis] = useState<any>(null);
    const [analysisLoading, setAnalysisLoading] = useState(false);
    const [logs, setLogs] = useState<any[]>([]);
    const [logsLoading, setLogsLoading] = useState(false);
    const [expandedHint, setExpandedHint] = useState<string | null>(null);
    const [activeSection, setActiveSection] = useState<'suggestions' | 'logs' | 'tree'>('suggestions');

    // Fetch all repos for picker
    useEffect(() => {
        api.getRepositories()
            .then((r: any) => setRepos(Array.isArray(r) ? r : (r?.repositories || [])))
            .catch(() => setRepos([]))
            .finally(() => setReposLoading(false));
    }, []);

    // Fetch analysis when repo selected
    const loadRepo = useCallback(async (repo: Repo) => {
        setAnalysisLoading(true);
        setLogsLoading(true);
        setAnalysis(null);
        setLogs([]);
        try {
            const a = await api.getRepoAnalysis(repo.id);
            setAnalysis(a);
        } catch { /* no analysis yet — that's fine */ }
        finally { setAnalysisLoading(false); }
        try {
            const l: any = await api.getRepoLogs(repo.id);
            setLogs(l?.logs || []);
        } catch { /* ignore */ }
        finally { setLogsLoading(false); }
    }, []);

    const handleSelect = (repo: Repo) => {
        setSelectedRepo(repo);
        setExpandedHint(null);
        setActiveSection('suggestions');
        loadRepo(repo);
    };

    const handleBack = () => {
        setSelectedRepo(null);
        setAnalysis(null);
        setLogs([]);
    };

    // ── No repo selected — show picker ──────────────────────────
    if (!selectedRepo) {
        return (
            <RepoPicker
                repos={repos}
                loading={reposLoading}
                onSelect={handleSelect}
            />
        );
    }

    // ── Repo selected — developer view ──────────────────────────
    const lang = selectedRepo.primary_language || selectedRepo.language || analysis?.primary_language;
    const hints = getHints(lang);
    const lc = LANG_COLORS[lang?.toLowerCase() || ''] || LANG_COLORS.default;

    // Build file tree
    const treePaths: string[] = analysis?.file_tree?.map((f: any) => f.path || f.name || '') || [];
    const treeNodes = treePaths.length > 0 ? buildTree(treePaths) : [];

    // Stats from analysis
    const totalFiles = analysis?.total_files || treePaths.length || 0;
    const linesOfCode = analysis?.total_loc || analysis?.loc || 0;
    const issuesCount = analysis?.issues_found || 0;

    return (
        <div style={{ display: 'flex', height: '100%', minHeight: '100vh', background: '#F8FAFC' }}>

            {/* LEFT: Dark sidebar — file tree */}
            <div style={{ width: 260, flexShrink: 0, background: '#1E1E2E', display: 'flex', flexDirection: 'column', borderRight: '1px solid #2D2D3F' }}>
                {/* Repo header */}
                <div style={{ padding: '14px 14px 10px', borderBottom: '1px solid #2D2D3F' }}>
                    <button
                        onClick={handleBack}
                        style={{ border: 'none', background: 'none', cursor: 'pointer', color: '#64748B', fontSize: 11, marginBottom: 10, display: 'flex', alignItems: 'center', gap: 4, padding: 0 }}
                    >
                        ← All repositories
                    </button>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{ width: 32, height: 32, borderRadius: 8, background: `${lc}20`, border: `1.5px solid ${lc}50`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                            <Code2 size={14} color={lc} />
                        </div>
                        <div style={{ minWidth: 0 }}>
                            <div style={{ fontSize: 12, fontWeight: 700, color: '#C7D2FE', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {selectedRepo.name}
                            </div>
                            {selectedRepo.owner && (
                                <div style={{ fontSize: 10, color: '#64748B' }}>{selectedRepo.owner}</div>
                            )}
                        </div>
                    </div>
                    {lang && (
                        <div style={{ marginTop: 8, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                            <span style={{ fontSize: 10, fontWeight: 700, color: lc, background: `${lc}20`, padding: '2px 8px', borderRadius: 20 }}>
                                {lang}
                            </span>
                            {totalFiles > 0 && <span style={{ fontSize: 10, color: '#64748B' }}>{totalFiles} files</span>}
                            {linesOfCode > 0 && <span style={{ fontSize: 10, color: '#64748B' }}>{linesOfCode.toLocaleString()} loc</span>}
                        </div>
                    )}
                </div>

                {/* File tree */}
                <div style={{ padding: '8px 6px 4px', borderBottom: '1px solid #2D2D3F' }}>
                    <span style={{ fontSize: 10, fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.08em', padding: '0 8px' }}>
                        Files
                    </span>
                </div>
                <div style={{ flex: 1, overflowY: 'auto', padding: '4px 0' }}>
                    {analysisLoading ? (
                        <div style={{ padding: 20, textAlign: 'center', color: '#475569' }}>
                            <Loader2 size={16} style={{ animation: 'spin 1s linear infinite', margin: '0 auto 6px' }} />
                            <div style={{ fontSize: 11 }}>Fetching tree…</div>
                            <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
                        </div>
                    ) : treeNodes.length === 0 ? (
                        <div style={{ padding: '16px 14px', fontSize: 11, color: '#475569' }}>
                            No file tree available. Repository may not be analyzed yet.
                        </div>
                    ) : (
                        treeNodes.map(node => <TreeNodeView key={node.path} node={node} />)
                    )}
                </div>

                {/* Repo link */}
                {(analysis?.repo_url || selectedRepo.repo_url) && (
                    <div style={{ padding: '10px 14px', borderTop: '1px solid #2D2D3F' }}>
                        <a
                            href={analysis?.repo_url || selectedRepo.repo_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: '#818CF8', textDecoration: 'none', fontWeight: 600 }}
                        >
                            <GitBranch size={12} /> View on GitHub <ExternalLink size={10} />
                        </a>
                    </div>
                )}
            </div>

            {/* RIGHT: Main content */}
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

                {/* Top bar */}
                <div style={{
                    padding: '14px 24px', background: '#fff', borderBottom: '1px solid #E2E8F0',
                    display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap',
                }}>
                    <div style={{ flex: 1 }}>
                        <h2 style={{ margin: 0, fontSize: 16, fontWeight: 800, color: '#0F172A' }}>
                            {selectedRepo.owner ? `${selectedRepo.owner}/` : ''}{selectedRepo.name}
                        </h2>
                        {selectedRepo.description && (
                            <p style={{ margin: '3px 0 0', fontSize: 12, color: '#64748B' }}>{selectedRepo.description}</p>
                        )}
                    </div>
                    {/* Quick stats */}
                    <div style={{ display: 'flex', gap: 16 }}>
                        {[
                            { label: 'Language', value: lang || 'Unknown', color: lc },
                            { label: 'Files', value: totalFiles > 0 ? totalFiles : '—', color: '#6366F1' },
                            { label: 'Issues', value: issuesCount > 0 ? issuesCount : '—', color: issuesCount > 0 ? '#EF4444' : '#94A3B8' },
                        ].map(stat => (
                            <div key={stat.label} style={{ textAlign: 'center' }}>
                                <div style={{ fontSize: 15, fontWeight: 800, color: stat.color }}>{stat.value}</div>
                                <div style={{ fontSize: 10, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{stat.label}</div>
                            </div>
                        ))}
                    </div>
                    <button
                        onClick={() => loadRepo(selectedRepo)}
                        style={{ border: '1px solid #E2E8F0', background: '#fff', cursor: 'pointer', padding: '7px 12px', borderRadius: 8, display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, color: '#64748B' }}
                    >
                        <RefreshCw size={13} /> Refresh
                    </button>
                </div>

                {/* Section tabs */}
                <div style={{ background: '#fff', borderBottom: '1px solid #E2E8F0', padding: '0 24px', display: 'flex', gap: 0 }}>
                    {[
                        { id: 'suggestions', label: 'AI Suggestions', icon: <Sparkles size={13} />, count: hints.length },
                        { id: 'logs', label: 'Logs', icon: <Activity size={13} />, count: logs.length },
                        { id: 'tree', label: 'Overview', icon: <FolderOpen size={13} /> },
                    ].map(tab => (
                        <button
                            key={tab.id}
                            onClick={() => setActiveSection(tab.id as any)}
                            style={{
                                display: 'flex', alignItems: 'center', gap: 6,
                                padding: '10px 18px', border: 'none', background: 'none', cursor: 'pointer',
                                fontSize: 13, fontWeight: activeSection === tab.id ? 700 : 500,
                                color: activeSection === tab.id ? '#6366F1' : '#64748B',
                                borderBottom: `2px solid ${activeSection === tab.id ? '#6366F1' : 'transparent'}`,
                                marginBottom: -1, transition: 'all 0.15s',
                            }}
                        >
                            {tab.icon}
                            {tab.label}
                            {tab.count !== undefined && tab.count > 0 && (
                                <span style={{ fontSize: 10, fontWeight: 700, background: activeSection === tab.id ? '#EEF2FF' : '#F1F5F9', color: activeSection === tab.id ? '#6366F1' : '#94A3B8', padding: '1px 6px', borderRadius: 10 }}>
                                    {tab.count}
                                </span>
                            )}
                        </button>
                    ))}
                </div>

                {/* Content area */}
                <div style={{ flex: 1, overflowY: 'auto', padding: 24 }}>

                    {/* ── AI Suggestions tab ─────────────────────── */}
                    {activeSection === 'suggestions' && (
                        <div style={{ maxWidth: 780 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
                                <div style={{ width: 36, height: 36, borderRadius: 10, background: '#EEF2FF', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                    <Brain size={18} color="#6366F1" />
                                </div>
                                <div>
                                    <div style={{ fontSize: 15, fontWeight: 700, color: '#0F172A' }}>
                                        AI Code Insights — {lang || 'General'}
                                    </div>
                                    <div style={{ fontSize: 12, color: '#64748B' }}>
                                        {hints.length} curated improvement suggestions for {lang || 'your codebase'}
                                    </div>
                                </div>
                            </div>
                            {hints.map(hint => (
                                <HintCard
                                    key={hint.id}
                                    hint={hint}
                                    expanded={expandedHint === hint.id}
                                    onToggle={() => setExpandedHint(expandedHint === hint.id ? null : hint.id)}
                                />
                            ))}
                        </div>
                    )}

                    {/* ── Logs tab ──────────────────────────────── */}
                    {activeSection === 'logs' && (
                        <div style={{ maxWidth: 860 }}>
                            <div style={{ fontSize: 14, fontWeight: 700, color: '#0F172A', marginBottom: 16 }}>Recent Logs</div>
                            {logsLoading ? (
                                <div style={{ textAlign: 'center', padding: 40, color: '#94A3B8' }}>
                                    <Loader2 size={20} style={{ animation: 'spin 1s linear infinite', marginBottom: 8 }} />
                                    <div style={{ fontSize: 13 }}>Loading logs…</div>
                                </div>
                            ) : logs.length === 0 ? (
                                <div style={{ textAlign: 'center', padding: 48, background: '#fff', borderRadius: 12, border: '1px solid #E2E8F0' }}>
                                    <Clock size={28} color="#94A3B8" style={{ marginBottom: 10 }} />
                                    <div style={{ fontSize: 14, color: '#64748B', fontWeight: 600 }}>No logs available</div>
                                    <div style={{ fontSize: 12, color: '#94A3B8', marginTop: 4 }}>
                                        Logs will appear once the repository monitor collects events.
                                    </div>
                                </div>
                            ) : (
                                <div style={{ background: '#1E1E2E', borderRadius: 12, overflow: 'hidden', border: '1px solid #2D2D3F' }}>
                                    {logs.slice(0, 100).map((log: any, i) => (
                                        <div
                                            key={i}
                                            style={{
                                                display: 'flex', gap: 12, padding: '8px 16px',
                                                borderBottom: i < logs.length - 1 ? '1px solid #2D2D3F' : 'none',
                                                fontFamily: 'monospace', fontSize: 12,
                                            }}
                                        >
                                            <span style={{ color: '#475569', flexShrink: 0 }}>
                                                {log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : `#${i + 1}`}
                                            </span>
                                            <span style={{ color: { error: '#EF4444', warning: '#EAB308', info: '#3B82F6' }[log.level as string] || '#94A3B8', flexShrink: 0, width: 56 }}>
                                                {(log.level || 'info').toUpperCase()}
                                            </span>
                                            <span style={{ color: '#C7D2FE', flex: 1, wordBreak: 'break-all' }}>
                                                {log.message || log.content || JSON.stringify(log)}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    {/* ── Overview tab ───────────────────────────── */}
                    {activeSection === 'tree' && (
                        <div style={{ maxWidth: 860 }}>
                            <div style={{ fontSize: 14, fontWeight: 700, color: '#0F172A', marginBottom: 16 }}>Repository Overview</div>
                            {analysisLoading ? (
                                <div style={{ textAlign: 'center', padding: 48, color: '#94A3B8' }}>
                                    <Loader2 size={20} style={{ animation: 'spin 1s linear infinite', marginBottom: 8 }} />
                                    <div style={{ fontSize: 13 }}>Loading overview…</div>
                                </div>
                            ) : !analysis ? (
                                <div style={{ textAlign: 'center', padding: 48, background: '#fff', borderRadius: 12, border: '1px solid #E2E8F0' }}>
                                    <Globe size={28} color="#94A3B8" style={{ marginBottom: 10 }} />
                                    <div style={{ fontSize: 14, color: '#64748B', fontWeight: 600 }}>No analysis data yet</div>
                                    <div style={{ fontSize: 12, color: '#94A3B8', marginTop: 4 }}>
                                        Connect this repository and wait for the first scan to complete.
                                    </div>
                                </div>
                            ) : (
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                                    {[
                                        { label: 'Primary Language', value: analysis.primary_language || lang || 'Unknown' },
                                        { label: 'Total Files', value: analysis.total_files?.toLocaleString() || '—' },
                                        { label: 'Lines of Code', value: analysis.total_loc?.toLocaleString() || '—' },
                                        { label: 'Open Issues', value: analysis.issues_found?.toString() || '0' },
                                        { label: 'Default Branch', value: analysis.branch || 'main' },
                                        { label: 'Last Analyzed', value: analysis.analyzed_at ? new Date(analysis.analyzed_at).toLocaleString() : '—' },
                                    ].map(item => (
                                        <div key={item.label} style={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: 12, padding: '14px 18px' }}>
                                            <div style={{ fontSize: 11, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>{item.label}</div>
                                            <div style={{ fontSize: 18, fontWeight: 700, color: '#0F172A' }}>{item.value}</div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                </div>
            </div>
        </div>
    );
}
