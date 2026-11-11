"""Turns a public GitHub repository into a snapshot the verifier can reason over.

About 8 + (number of modules) API calls per repository. File contents come from
raw.githubusercontent.com, which does not use the API rate limit.
"""
import os
import re
from datetime import datetime, timezone

import httpx

API = "https://api.github.com"
CODE_EXT = (".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rb", ".php", ".cs", ".kt", ".rs", ".sql", ".c", ".cpp")
SKIP_DIRS = {"docs", "doc", "test", "tests", "__tests__", "node_modules", "dist", "build", "vendor", "examples",
             "example", "scripts", "assets", "static", "public", "migrations_archive"}
MAX_MODULES = 8
MAX_CODE_FILES = 45
MAX_DOC_FILES = 8
MAX_FILE_BYTES = 60_000


class GitHubError(Exception):
    pass


def parse_repo(value):
    m = re.search(r"(?:github\.com[/:])?([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", value.strip())
    if not m:
        raise GitHubError("Enter a repository as owner/name or a github.com URL.")
    return f"{m.group(1)}/{m.group(2)}"


def is_code(path):
    return path.lower().endswith(CODE_EXT)


def is_doc(path):
    p = path.lower()
    skip = ("license", "changelog", "changes", "contributing", "code_of_conduct", "security", ".github/", "template")
    return p.endswith((".md", ".rst")) and not any(x in p for x in skip)


def is_test(path):
    p = path.lower()
    return p.startswith(("tests/", "test/")) or "/tests/" in p or "/test/" in p or "__tests__" in p or \
        os.path.basename(p).startswith("test_") or ".test." in p or ".spec." in p


def pick_modules(paths):
    """Modules are the top-level code folders. If the code sits in one folder (src/, app/, a package), look inside it."""
    def groups(prefix):
        g = {}
        for p in paths:
            if not is_code(p) or is_test(p) or not p.startswith(prefix):
                continue
            rest = p[len(prefix):]
            head = rest.split("/")[0]
            if "/" not in rest:
                g.setdefault(prefix + head, 0)  # a file directly in this folder
                g[prefix + head] += 1
            elif head.lower() not in SKIP_DIRS and not head.startswith("."):
                g.setdefault(prefix + head + "/", 0)
                g[prefix + head + "/"] += 1
        return g

    prefix = ""
    for _ in range(4):  # walk down through wrappers such as src/ or a single package folder
        g = groups(prefix)
        if len(g) == 1 and next(iter(g)).endswith("/"):
            prefix = next(iter(g))
        else:
            break
    dirs = {k: v for k, v in g.items() if k.endswith("/")}
    chosen = dirs if len(dirs) >= 2 else g
    ranked = sorted(chosen.items(), key=lambda kv: (-kv[1], kv[0]))[:MAX_MODULES]
    return sorted(k for k, _ in ranked)


def pick_files(paths, sizes, modules):
    docs = [p for p in paths if is_doc(p) and sizes.get(p, 0) < MAX_FILE_BYTES]
    docs.sort(key=lambda p: (not os.path.basename(p).lower().startswith("readme"), p.count("/"), p))
    code = []
    per_module = max(3, MAX_CODE_FILES // max(len(modules), 1))
    for m in modules:
        inside = [p for p in paths if (p == m or p.startswith(m)) and is_code(p) and 0 < sizes.get(p, 1) < MAX_FILE_BYTES]
        inside.sort(key=lambda p: (p.count("/"), -sizes.get(p, 0)))
        code += inside[:per_module]
    tests = [p for p in paths if is_test(p) and is_code(p) and sizes.get(p, 0) < MAX_FILE_BYTES][:8]
    return docs[:MAX_DOC_FILES], code[:MAX_CODE_FILES], tests


def _commit(c, repo):
    return {
        "sha": c["sha"],
        "author": (c["commit"]["author"] or {}).get("name") or ((c.get("author") or {}).get("login")) or "unknown",
        "date": (c["commit"]["author"] or {}).get("date", "")[:10],
        "message": c["commit"]["message"].split("\n")[0][:200],
        "url": f"https://github.com/{repo}/commit/{c['sha']}",
    }


def fetch_snapshot(repo_input, token=None):
    repo = parse_repo(repo_input)
    token = token or os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "knowflow-ai"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with httpx.Client(timeout=20, headers=headers, follow_redirects=True) as http:
        def get(url, **params):
            r = http.get(API + url, params=params)
            if r.status_code == 404:
                raise GitHubError(f"Repository {repo} was not found, or it is private.")
            if r.status_code in (403, 429):
                raise GitHubError("GitHub rate limit reached. Set GITHUB_TOKEN on the server, or try again in an hour.")
            if r.status_code >= 400:
                raise GitHubError(f"GitHub returned {r.status_code} for {url}.")
            return r.json()

        info = get(f"/repos/{repo}")
        repo = info["full_name"]
        branch = info["default_branch"]
        tree = get(f"/repos/{repo}/git/trees/{branch}", recursive="1")
        blobs = [t for t in tree.get("tree", []) if t["type"] == "blob"]
        paths = [t["path"] for t in blobs]
        sizes = {t["path"]: t.get("size", 0) for t in blobs}
        modules = pick_modules(paths)
        docs, code, tests = pick_files(paths, sizes, modules)

        module_commits = {m: [_commit(c, repo) for c in get(f"/repos/{repo}/commits", path=m.rstrip("/"), per_page=100)]
                          for m in modules}
        readme = next((p for p in docs if os.path.basename(p).lower().startswith("readme")), None)
        readme_commits = [_commit(c, repo) for c in get(f"/repos/{repo}/commits", path=readme, per_page=3)] if readme else []

        issues = []
        for i in get(f"/repos/{repo}/issues", state="open", per_page=30):
            issues.append({
                "number": i["number"], "title": i["title"], "url": i["html_url"], "is_pr": "pull_request" in i,
                "author": (i.get("user") or {}).get("login", ""),
                "assignee": (i.get("assignee") or {}).get("login", ""),
                "updated": i.get("updated_at", "")[:10],
            })

        files = {}
        raw = httpx.Client(timeout=20, follow_redirects=True)
        for p in docs + code + tests:
            r = raw.get(f"https://raw.githubusercontent.com/{repo}/{branch}/{p}")
            if r.status_code == 200:
                try:
                    files[p] = r.content.decode("utf-8")
                except UnicodeDecodeError:
                    pass
        raw.close()

    return {
        "repo": repo, "branch": branch, "description": info.get("description") or "",
        "tree": paths, "modules": modules, "files": files, "module_commits": module_commits,
        "readme": readme, "readme_commits": readme_commits, "issues": issues,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }
