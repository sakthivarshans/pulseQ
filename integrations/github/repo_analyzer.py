"""
integrations/github/repo_analyzer.py
──────────────────────────────────────
Real GitHub repository analyzer.
Fetches actual data via GitHub REST API v3.
Analyzes code with Phi-3 (if available) and Gemini for the summary card.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import time
from datetime import UTC, datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Try to import Motor for MongoDB storage
try:
    from bson import ObjectId
    _BSON_OK = True
except ImportError:
    _BSON_OK = False

# ── Source file extensions ────────────────────────────────────────────────────
SOURCE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rb",
    ".php", ".cs", ".cpp", ".c", ".h", ".swift", ".kt", ".rs",
    ".scala", ".sh", ".bash", ".yaml", ".yml", ".tf", ".sql",
}

# ── Dependency file names ─────────────────────────────────────────────────────
DEP_FILES = {
    "package.json", "requirements.txt", "Pipfile", "pyproject.toml",
    "pom.xml", "build.gradle", "go.mod", "Gemfile", "composer.json",
    "Cargo.toml",
}

# Language detection map
EXT_TO_LANG = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".tsx": "typescript", ".jsx": "javascript", ".java": "java",
    ".go": "go", ".rb": "ruby", ".php": "php", ".cs": "csharp",
    ".cpp": "cpp", ".c": "c", ".h": "c", ".swift": "swift",
    ".kt": "kotlin", ".rs": "rust", ".scala": "scala",
}

in_memory_store: dict[str, dict] = {}   # repo_id -> full analysis result
feedback_store: dict[str, dict] = {}    # issue_id -> {upvotes, downvotes}


class GitHubRepoAnalyzer:
    """Analyzes a real GitHub repository via the REST API."""

    def __init__(self, token: str, ollama_url: str = "http://localhost:11434",
                 gemini_provider=None, mongo_db=None):
        self.token = token
        self.ollama_url = ollama_url
        self.gemini = gemini_provider
        self.mongo_db = mongo_db  # Optional Motor MongoDB database
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Public entry point
    # ─────────────────────────────────────────────────────────────────────────
    async def analyze(self, repo_url: str) -> dict[str, Any]:
        """Full analysis pipeline. Returns structured result."""
        owner, repo = self._parse_url(repo_url)
        repo_id = f"{owner}/{repo}"

        logger.info(f"Starting analysis of {repo_id}")
        t0 = time.monotonic()

        async with httpx.AsyncClient(headers=self.headers, timeout=30) as client:
            # Step A — real metadata
            meta = await self._fetch_metadata(client, owner, repo)
            default_branch = meta.get("default_branch", "main")

            # Step B — file tree + LOC
            tree_result = await self._fetch_file_tree(client, owner, repo, default_branch)
            all_files = tree_result["files"]
            source_files = [f for f in all_files if self._is_source(f["path"])]
            dep_files_found = [f for f in all_files if f["path"].split("/")[-1] in DEP_FILES]

            # Fetch source file contents (cap at 50 to stay under GitHub Rate limit)
            file_contents = await self._fetch_file_contents(
                client, owner, repo, source_files[:50]
            )

            # Step C — dependency count
            dep_data = await self._count_deps(client, owner, repo, dep_files_found[:5])

            # Step D — code structure
            code_structure = self._analyze_structure(file_contents)

            # Step E — real issues via Phi-3
            issues = await self._detect_issues_phi3(file_contents)

            # Add issue IDs and feedback init
            for issue in issues:
                issue_id = f"{repo_id}/{issue['file']}/{issue['line_number']}"
                issue["issue_id"] = issue_id.replace("/", "_").replace(".", "_")
                feedback_store.setdefault(issue["issue_id"],
                                          {"upvotes": 0, "downvotes": 0})

            # Step F — Gemini high-level analysis
            gemini_analysis = await self._gemini_analysis(repo_id, meta, issues,
                                                          code_structure, dep_data)

            elapsed = round(time.monotonic() - t0, 1)

            result = {
                "repo_id": repo_id,
                "repo_url": repo_url,
                "owner": owner,
                "name": repo,
                "description": meta.get("description") or "",
                "language": meta.get("language") or "Unknown",
                "stars": meta.get("stargazers_count", 0),
                "forks": meta.get("forks_count", 0),
                "default_branch": default_branch,
                "created_at": meta.get("created_at", ""),
                "pushed_at": meta.get("pushed_at", ""),
                "topics": meta.get("topics", []),
                # Real counts
                "total_files": len(all_files),
                "source_files": len(source_files),
                "total_loc": sum(c["loc"] for c in file_contents.values()),
                "total_dependencies": dep_data["total"],
                "dependency_details": dep_data["details"],
                "issues_found": len(issues),
                "issues": issues,
                # Structure
                "code_structure": code_structure,
                "language_breakdown": code_structure["files_by_type"],
                "file_tree": [
                    {
                        "path": f["path"],
                        "name": f["path"].split("/")[-1],
                        "type": "file" if f["type"] == "blob" else "dir",
                        "size": f.get("size", 0),
                        "loc": file_contents.get(f["path"], {}).get("loc"),
                        "risk": self._risk_score(f["path"], issues),
                        "issues": sum(1 for i in issues if i["file"] == f["path"]),
                    }
                    for f in all_files[:200]  # cap for frontend rendering
                ],
                # Analysis
                "gemini_analysis": gemini_analysis,
                "analyzed_at": datetime.now(UTC).isoformat(),
                "analysis_duration_s": elapsed,
                "status": "active",
                "last_commit": meta.get("pushed_at", ""),
                "open_issues_count": meta.get("open_issues_count", 0),
            }

        in_memory_store[repo_id] = result
        logger.info(f"Analysis complete: {repo_id} in {elapsed}s, "
                    f"{result['total_files']} files, {result['total_loc']} LOC, "
                    f"{len(issues)} issues")

        # Save errors to MongoDB if available
        if self.mongo_db is not None and issues:
            await self._save_errors_to_mongo(repo_id, repo, issues)

        return result

    async def _save_errors_to_mongo(self, repo_id: str, repo_name: str,
                                     issues: list[dict]) -> None:
        """Persist detected errors to MongoDB repo_errors collection."""
        analysis_id = str(int(time.time()))  # unix timestamp as analysis ID
        docs = []
        for issue in issues:
            doc = {
                "repo_id": repo_id,
                "repo_name": repo_name,
                "analysis_id": analysis_id,
                "file_path": issue.get("file", issue.get("file_path", "")),
                "line_number": issue.get("line_number", 1),
                "language": issue.get("language", ""),
                "error_type": issue.get("issue_type", issue.get("error_type", "unknown")),
                "severity": issue.get("severity", "P3"),
                "title": issue.get("title", issue.get("description", ""))[:200],
                "description": issue.get("description", ""),
                "suggestion": issue.get("suggestion", ""),
                "code_before": issue.get("code_before", "")[:1000],
                "code_after": issue.get("code_after", "")[:1000],
                "confidence_score": float(issue.get("confidence_score", 0.8)),
                "source": issue.get("source", "static"),
                "upvotes": 0,
                "downvotes": 0,
                "resolved": False,
                "created_at": datetime.now(UTC),
                # Legacy compatibility fields
                "file": issue.get("file", issue.get("file_path", "")),
                "issue_type": issue.get("issue_type", issue.get("error_type", "unknown")),
                "issue_id": issue.get("issue_id", ""),
                "feedback": {"upvotes": 0, "downvotes": 0},
            }
            docs.append(doc)
        try:
            # Delete old analysis results for this repo before inserting new ones
            await self.mongo_db["repo_errors"].delete_many(
                {"repo_id": repo_id, "analysis_id": {"$ne": analysis_id}}
            )
            await self.mongo_db["repo_errors"].insert_many(docs, ordered=False)
            logger.info(f"Saved {len(docs)} errors to MongoDB for {repo_id}")
        except Exception as exc:
            logger.warning(f"MongoDB error save failed for {repo_id}: {exc}")

    # ─────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────────
    def _parse_url(self, url: str) -> tuple[str, str]:
        """Parse GitHub URL or owner/repo string into (owner, repo)."""
        url = url.strip().rstrip("/")
        if url.startswith("http"):
            parts = url.split("/")
            return parts[-2], parts[-1].replace(".git", "")
        if "/" in url:
            parts = url.split("/")
            return parts[0], parts[1].replace(".git", "")
        raise ValueError(f"Cannot parse repo URL: {url}")

    def _is_source(self, path: str) -> bool:
        ext = "." + path.rsplit(".", 1)[-1] if "." in path else ""
        return ext.lower() in SOURCE_EXTENSIONS

    def _risk_score(self, path: str, issues: list[dict]) -> float:
        file_issues = [i for i in issues if i["file"] == path]
        if not file_issues:
            return 0.0
        max_sev = max(
            {"P1": 1.0, "P2": 0.75, "P3": 0.5, "P4": 0.25}.get(i["severity"], 0.25)
            for i in file_issues
        )
        return min(1.0, max_sev + (len(file_issues) - 1) * 0.05)

    async def _fetch_metadata(self, client: httpx.AsyncClient, owner: str, repo: str) -> dict:
        resp = await client.get(f"https://api.github.com/repos/{owner}/{repo}")
        resp.raise_for_status()
        return resp.json()

    async def _fetch_file_tree(self, client: httpx.AsyncClient,
                                owner: str, repo: str, branch: str) -> dict:
        resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
        )
        if resp.status_code != 200:
            return {"files": []}
        data = resp.json()
        files = [
            {"path": item["path"], "type": item["type"], "size": item.get("size", 0)}
            for item in data.get("tree", [])
            if item["type"] in ("blob", "tree")
        ]
        return {"files": files, "truncated": data.get("truncated", False)}

    async def _fetch_file_contents(
        self, client: httpx.AsyncClient, owner: str, repo: str,
        files: list[dict]
    ) -> dict[str, dict]:
        """Fetch content of source files. Returns {path: {content, loc}}."""
        results: dict[str, dict] = {}

        async def fetch_one(f: dict) -> None:
            try:
                resp = await client.get(
                    f"https://api.github.com/repos/{owner}/{repo}/contents/{f['path']}"
                )
                if resp.status_code != 200:
                    return
                data = resp.json()
                if data.get("encoding") == "base64":
                    content = base64.b64decode(data["content"].replace("\n", "")).decode(
                        "utf-8", errors="replace"
                    )
                    results[f["path"]] = {
                        "content": content,
                        "loc": len([l for l in content.splitlines() if l.strip()]),
                    }
            except Exception as e:
                logger.debug(f"Failed to fetch {f['path']}: {e}")

        # Throttle: fetch 10 at a time
        for i in range(0, len(files), 10):
            batch = files[i: i + 10]
            await asyncio.gather(*[fetch_one(f) for f in batch])
            await asyncio.sleep(0.5)  # respect rate limits

        return results

    async def _count_deps(
        self, client: httpx.AsyncClient, owner: str, repo: str,
        dep_files: list[dict]
    ) -> dict[str, Any]:
        total = 0
        details: list[dict] = []

        for f in dep_files:
            name = f["path"].split("/")[-1]
            try:
                resp = await client.get(
                    f"https://api.github.com/repos/{owner}/{repo}/contents/{f['path']}"
                )
                if resp.status_code != 200:
                    continue
                data = resp.json()
                if data.get("encoding") != "base64":
                    continue
                content = base64.b64decode(data["content"].replace("\n", "")).decode(
                    "utf-8", errors="replace"
                )
                count, pkgs = self._parse_dep_file(name, content)
                total += count
                details.append({"file": f["path"], "count": count, "packages": pkgs[:10]})
            except Exception as e:
                logger.debug(f"Dep parse error {f['path']}: {e}")

        return {"total": total, "details": details}

    def _parse_dep_file(self, filename: str, content: str) -> tuple[int, list[str]]:
        pkgs: list[str] = []
        if filename == "package.json":
            try:
                j = json.loads(content)
                deps = list(j.get("dependencies", {}).keys())
                dev = list(j.get("devDependencies", {}).keys())
                pkgs = deps + dev
            except Exception:
                pass
        elif filename == "requirements.txt":
            pkgs = [l.strip().split("==")[0].split(">=")[0].split("[")[0]
                    for l in content.splitlines()
                    if l.strip() and not l.startswith("#")]
        elif filename == "pyproject.toml":
            in_deps = False
            for line in content.splitlines():
                if "[tool.poetry.dependencies]" in line or "[dependencies]" in line:
                    in_deps = True
                    continue
                if in_deps and line.startswith("["):
                    in_deps = False
                if in_deps and "=" in line:
                    pkgs.append(line.split("=")[0].strip().strip('"'))
        elif filename == "go.mod":
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("require "):
                    pkgs.append(line.split()[1])
                elif line and "/" in line and not line.startswith("//"):
                    parts = line.split()
                    if len(parts) >= 2:
                        pkgs.append(parts[0])
        elif filename == "Gemfile":
            pkgs = [re.findall(r"gem ['\"]([^'\"]+)['\"]", l)[0]
                    for l in content.splitlines()
                    if l.strip().startswith("gem") and re.findall(r"gem ['\"]([^'\"]+)['\"]", l)]
        elif filename == "composer.json":
            try:
                j = json.loads(content)
                pkgs = list(j.get("require", {}).keys()) + list(j.get("require-dev", {}).keys())
            except Exception:
                pass
        return len(pkgs), pkgs

    def _analyze_structure(self, file_contents: dict[str, dict]) -> dict[str, Any]:
        """Extract real structural info from file contents."""
        files_by_type: dict[str, int] = {}
        functions_total = 0
        classes_total = 0
        api_endpoints: list[str] = []
        complexity_scores: dict[str, int] = {}

        # Regex patterns per language
        func_patterns = [
            r"^def\s+(\w+)\s*\(",              # Python
            r"^async def\s+(\w+)\s*\(",         # Python async
            r"function\s+(\w+)\s*\(",           # JS/TS
            r"(const|let|var)\s+(\w+)\s*=\s*(async\s*)?\(",  # JS arrow
            r"public\s+\w+\s+(\w+)\s*\(",       # Java/C#
            r"func\s+(\w+)\s*\(",               # Go
            r"def\s+(\w+)",                     # Ruby
        ]
        class_patterns = [
            r"^class\s+(\w+)",
            r"^interface\s+(\w+)",
            r"^struct\s+(\w+)",
        ]
        route_patterns = [
            r'@app\.(get|post|put|delete|patch)\(["\']([^"\']+)["\']',  # FastAPI/Flask
            r'router\.(get|post|put|delete)\(["\']([^"\']+)["\']',      # Express
            r'@(Get|Post|Put|Delete|Patch)\(["\']([^"\']+)["\']',       # Spring/NestJS
            r"path\(['\"]([^'\"]+)['\"]",                                # Django
        ]
        complexity_ops = ["if ", "elif ", "else:", "for ", "while ", "try:", "except"]

        for path, data in file_contents.items():
            ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
            files_by_type[ext] = files_by_type.get(ext, 0) + 1

            content = data.get("content", "")
            lines = content.splitlines()

            # Count functions
            for line in lines:
                for pat in func_patterns:
                    if re.search(pat, line):
                        functions_total += 1
                        break

            # Count classes
            for line in lines:
                for pat in class_patterns:
                    if re.match(pat, line.strip()):
                        classes_total += 1
                        break

            # Detect API routes
            for line in lines:
                for pat in route_patterns:
                    m = re.search(pat, line)
                    if m:
                        groups = m.groups()
                        if len(groups) >= 2:
                            api_endpoints.append(f"{groups[0].upper()} {groups[1]}")
                        break

            # Complexity score
            complexity = sum(1 for line in lines
                             for op in complexity_ops if op in line)
            if complexity > 0:
                complexity_scores[path] = complexity

        return {
            "files_by_type": files_by_type,
            "total_functions": functions_total,
            "total_classes": classes_total,
            "api_endpoints": api_endpoints[:50],
            "complexity_scores": dict(sorted(
                complexity_scores.items(), key=lambda x: x[1], reverse=True
            )[:20]),
        }

    async def _detect_issues_phi3(
        self, file_contents: dict[str, dict]
    ) -> list[dict[str, Any]]:
        """Analyze source files with Phi-3. Returns only real issues."""
        # Check if Ollama is reachable
        phi3_available = await self._phi3_available()
        issues: list[dict[str, Any]] = []

        for path, data in file_contents.items():
            ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
            lang = EXT_TO_LANG.get(ext, "")
            if not lang:
                continue

            content = data.get("content", "")
            if not content or len(content) < 50:
                continue

            if phi3_available:
                file_issues = await self._phi3_analyze_file(path, content, lang)
            else:
                file_issues = self._static_analyze_file(path, content, lang)

            issues.extend(file_issues)

        return issues

    async def _phi3_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{self.ollama_url}/api/tags")
                models = r.json().get("models", [])
                return any(m.get("name", "").startswith("phi3") for m in models)
        except Exception:
            return False

    async def _phi3_analyze_file(
        self, file_path: str, content: str, language: str
    ) -> list[dict[str, Any]]:
        """Call Phi-3 via Ollama to analyze a file."""
        prompt = (
            f"You are a senior {language} code reviewer.\n"
            f"Analyze this file for REAL issues only. File: {file_path}\n\n"
            f"```{language}\n{content[:3500]}\n```\n\n"
            "Reply with a JSON array. Each element:\n"
            '{"line_number": int, "issue_type": "missing_error_handling|security_vulnerability|'
            'performance_issue|null_pointer_risk|resource_leak|hardcoded_secret|'
            'missing_input_validation|deprecated_usage", "severity": "P1|P2|P3|P4", '
            '"description": "specific description", "suggestion": "exact fix", '
            '"code_before": "snippet", "code_after": "fixed"}\n\n'
            'If NO issues: reply with exactly []\nDo NOT invent issues.'
        )
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                resp = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={"model": "phi3:mini", "prompt": prompt, "stream": False,
                          "options": {"temperature": 0.1, "top_p": 0.9}},
                )
                text = resp.json().get("response", "[]")
                start = text.find("[")
                end = text.rfind("]") + 1
                if start >= 0 and end > start:
                    raw_issues = json.loads(text[start:end])
                    return [
                        {
                            "file": file_path,
                            "line_number": i.get("line_number", 1),
                            "issue_type": i.get("issue_type", "unknown"),
                            "severity": i.get("severity", "P3"),
                            "description": i.get("description", ""),
                            "suggestion": i.get("suggestion", ""),
                            "code_before": i.get("code_before", ""),
                            "code_after": i.get("code_after", ""),
                            "source": "phi3",
                        }
                        for i in raw_issues if isinstance(i, dict)
                    ]
        except Exception as e:
            logger.warning(f"Phi-3 analysis failed for {file_path}: {e}")
        return []

    def _static_analyze_file(
        self, file_path: str, content: str, language: str
    ) -> list[dict[str, Any]]:
        """Regex-based fallback analysis when Phi-3 is unavailable."""
        issues: list[dict] = []
        lines = content.splitlines()

        patterns = [
            # Hardcoded secrets
            (r'(?i)(password|secret|api_key|token)\s*=\s*["\'][^"\']{6,}["\']',
             "hardcoded_secret", "P1",
             "Hardcoded credential detected — use environment variable instead",
             "Move to environment variable: os.environ.get('VAR_NAME')"),
            # Bare except
            (r"^\s*except\s*:", "missing_error_handling", "P3",
             "Bare except catches all exceptions including SystemExit — specify exception type",
             "Use `except Exception as e:` or specific exception type"),
            # TODO/FIXME
            (r"(?i)#\s*(todo|fixme|hack|xxx):",
             "deprecated_usage", "P4",
             "TODO/FIXME comment left in production code",
             "Resolve or create a tracked ticket for this"),
            # Eval usage
            (r"\beval\s*\(", "security_vulnerability", "P1",
             "eval() is a security vulnerability — never use with user input",
             "Replace eval() with a safe alternative (ast.literal_eval, json.loads, etc.)"),
            # SQL injection risk
            (r'(?i)(execute|query)\s*\(\s*["\'].*%s.*["\']',
             "security_vulnerability", "P2",
             "Possible SQL injection via string interpolation",
             "Use parameterized queries: cursor.execute(sql, params)"),
        ]

        for lineno, line in enumerate(lines, start=1):
            for pattern, issue_type, severity, description, suggestion in patterns:
                if re.search(pattern, line):
                    issues.append({
                        "file": file_path,
                        "line_number": lineno,
                        "issue_type": issue_type,
                        "severity": severity,
                        "description": description,
                        "suggestion": suggestion,
                        "code_before": line.strip(),
                        "code_after": f"# Fix: {suggestion}",
                        "source": "static",
                    })
                    break  # one issue per line

        return issues

    async def _gemini_analysis(
        self, repo_id: str, meta: dict, issues: list[dict],
        structure: dict, dep_data: dict
    ) -> str:
        """Generate Gemini analysis card for the Developer Overview page."""
        if self.gemini is None:
            return self._fallback_analysis(repo_id, issues, structure)

        summary = {
            "repo": repo_id,
            "language": meta.get("language", "Unknown"),
            "stars": meta.get("stargazers_count", 0),
            "total_functions": structure.get("total_functions", 0),
            "total_classes": structure.get("total_classes", 0),
            "api_endpoints_found": len(structure.get("api_endpoints", [])),
            "issues_count": len(issues),
            "issues_by_severity": {
                sev: sum(1 for i in issues if i["severity"] == sev)
                for sev in ["P1", "P2", "P3", "P4"]
            },
            "total_dependencies": dep_data.get("total", 0),
            "languages_used": list(structure.get("files_by_type", {}).keys())[:10],
        }

        prompt = (
            f"You are an expert software architect reviewing the repository: {repo_id}.\n"
            f"Based on this REAL analysis data:\n{json.dumps(summary, indent=2)}\n\n"
            "Provide a concise technical assessment (max 200 words):\n"
            "1) Overall code health (be specific to the data)\n"
            "2) Top concerns based on actual findings\n"
            "3) Specific recommendations with file/area references\n"
            "4) Estimated engineering effort to address issues\n\n"
            "If issues_count is 0, say the code is clean. Never invent problems.\n"
            "Be direct and specific. No marketing language."
        )

        try:
            response = await self.gemini.generate(
                system_prompt="You are a software architect providing concise code reviews.",
                user_prompt=prompt,
                temperature=0.3,
                max_tokens=512,
            )
            return response
        except Exception as e:
            logger.warning(f"Gemini analysis failed: {e}")
            return self._fallback_analysis(repo_id, issues, structure)

    def _fallback_analysis(self, repo_id: str, issues: list[dict],
                            structure: dict) -> str:
        n = len(issues)
        if n == 0:
            return (f"Static analysis of **{repo_id}** completed. "
                    f"Found {structure.get('total_functions', 0)} functions across "
                    f"{sum(structure.get('files_by_type', {}).values())} source files. "
                    "No issues detected — code baseline is clean.")
        p1 = sum(1 for i in issues if i["severity"] == "P1")
        p2 = sum(1 for i in issues if i["severity"] == "P2")
        return (f"Analysis of **{repo_id}** found {n} issue(s): "
                f"{p1} critical (P1), {p2} high (P2). "
                "Review the Issues tab for detailed descriptions and suggested fixes.")
