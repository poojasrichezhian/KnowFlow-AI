# KnowFlow AI

Verified project handovers. KnowFlow reads a repository, notes, documents and a task list, checks every
statement against the other sources, and gives each claim its evidence and one of four states:
**Verified, Uncertain, Conflicting, Missing**. A project manager reviews and approves before anything is shared.

Team: Poojasri I S, Aadarshini S S, Surya Prakash M

## What it does

- **Evidence ledger.** Every claim shows where it was stated, what supports it and what contradicts it, with file and line or commit.
- **Deterministic verifier.** States are decided by rules over the evidence, never by a language model. Same sources, same result.
- **Four conflict checks.** A named owner against commit history, "done" against an open task or TODO, opposite wording about the
  same thing (asynchronous/synchronous, enabled/disabled), and documents that point at files which do not exist.
- **Facts read from the repository.** Who commits to each module, single-owner modules, imports between modules,
  TODO/FIXME/HACK notes, configuration the code reads but no document explains, modules without tests, open issues.
- **Departure simulator.** Pick a person: see the modules only they know and get an exit interview with one question per gap.
  Answers become evidence and move a Missing item to Uncertain, not straight to Verified.
- **Human review.** Approve, reject, edit, or resolve a conflict with a written reason. Conflicts cannot be approved unresolved.
- **Role-based handover.** Published versions with history. Managers, developers and new team members each see a different report.
- **Permissions.** JWT sign-in, project membership, roles, and managers-only sources whose claims are hidden from other roles.

## Run it locally

Needs Python 3.11+ and Node 18+.

```bash
cd frontend && npm install && npm run build && cd ..
cd backend && pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

Open http://localhost:8000 and choose a demo role. The demo project is created on first start.

Tests: `cd backend && pip install pytest && python -m pytest -q`

For frontend development run `npm run dev` in `frontend/` (it proxies `/api` to port 8000).

## Deploy (one Docker service)

The `Dockerfile` builds the frontend and serves it from the API, so there is a single URL.

1. Push this folder to a **public** GitHub repository.
2. On Render: New > Web Service > pick the repository > it detects the Dockerfile > Free plan.
   (Hugging Face Spaces with the Docker SDK also works: add `ENV PORT=7860` or set the Space's `app_port`.)
3. Set the environment variables from `.env.example`. `SECRET_KEY` and `GITHUB_TOKEN` matter most.
4. Open the URL in a private window and sign in with a demo role.

Free plans sleep when idle, so the first request can take up to a minute. Without `DATABASE_URL` the SQLite
file lives inside the container and is recreated on every restart (the demo project comes back, other accounts do not).

### Make the demo evidence links clickable

The demo project uses a small sample repository with a fictional team. To let anyone open its commits and files on GitHub:

```bash
python scripts/make_demo_repo.py payments-service-demo
cd payments-service-demo
git remote add origin https://github.com/YOUR_USER/payments-service-demo.git
git push -u origin main
```

Then set `DEMO_REPO=YOUR_USER/payments-service-demo` and restart. Commit hashes are fixed by the script, so the
bundled snapshot matches the pushed repository exactly.

## How a state is decided

| State | Rule |
| --- | --- |
| Verified | Counted or read directly from the repository, or stated in one source and backed by an independent one |
| Uncertain | Stated in one place only, or supported only by indirect evidence such as age |
| Conflicting | Two sources disagree. Only a reviewer can resolve it, with a written reason |
| Missing | Something a successor needs (config, tests, an owner, the reason for a decision) that no source explains |

Readiness is the share of claims that are verified and approved; unreviewed or single-source claims count in part,
open conflicts and gaps count for nothing.

## Layout

```
backend/app/engine.py         the verifier (pure function: sources in, claims out)
backend/app/github_ingest.py  GitHub REST API reader
backend/app/retrieval.py      TF-IDF evidence search
backend/app/main.py           FastAPI routes, review, versions, reports
backend/app/llm.py            optional LLM step with quote lock
backend/seed/                 bundled demo project
frontend/src/                 React interface
scripts/                      sample repository builder
```

## Known limits

See `ROUND2_SUBMISSION.md`.
