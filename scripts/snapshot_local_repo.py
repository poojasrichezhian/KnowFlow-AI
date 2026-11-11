"""Writes the same snapshot format as app/github_ingest.py, but from a local git clone.
Used once to bundle the demo project so it loads with no network access.

    python scripts/snapshot_local_repo.py ./payments-service-demo OWNER/payments-service-demo backend/seed/demo_snapshot.json
"""
import json, os, subprocess, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.github_ingest import pick_files, pick_modules  # noqa: E402


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def commits(cwd, repo, path, limit=100):
    out = git(cwd, "log", f"-{limit}", "--format=%H%x1f%an%x1f%ad%x1f%s", "--date=short", "--", path)
    rows = []
    for line in out.strip().splitlines():
        sha, author, date, msg = line.split("\x1f")
        rows.append({"sha": sha, "author": author, "date": date, "message": msg,
                     "url": f"https://github.com/{repo}/commit/{sha}"})
    return rows


def main(path, repo, dest):
    paths = git(path, "ls-files").strip().splitlines()
    sizes = {p: os.path.getsize(os.path.join(path, p)) for p in paths}
    modules = pick_modules(paths)
    docs, code, tests = pick_files(paths, sizes, modules)
    files = {p: open(os.path.join(path, p), encoding="utf-8").read() for p in docs + code + tests}
    readme = next((p for p in docs if os.path.basename(p).lower().startswith("readme")), None)
    snap = {
        "repo": repo, "branch": "main", "description": "Sample payments service used by the KnowFlow AI demo",
        "tree": paths, "modules": modules, "files": files,
        "module_commits": {m: commits(path, repo, m.rstrip("/")) for m in modules},
        "readme": readme, "readme_commits": commits(path, repo, readme, 3) if readme else [],
        "issues": [], "fetched_at": "bundled snapshot",
    }
    json.dump(snap, open(dest, "w"), indent=1)
    print("modules:", modules, "| files:", len(files))


if __name__ == "__main__":
    main(*sys.argv[1:4])
