# KnowFlow AI

**Verified project handovers.**

KnowFlow reads a repository, notes, documents, and a task list. It checks statements against available sources and gives each claim its evidence and one of four states: **Verified, Uncertain, Conflicting, or Missing**.

A project manager reviews and approves claims before anything is shared.

**Team:** Poojasri I S, Aadarshini S S, Surya Prakash M

## What It Does

- **Evidence Ledger:** Every claim shows where it was stated, what supports it, and what contradicts it, with file, line, or commit references.
- **Deterministic Verifier:** States are decided using rules over the evidence, not by a language model. The same sources produce the same results.
- **Four Conflict Checks:** Identifies a named owner against commit history, "done" claims against open tasks or TODOs, opposite wording about the same thing (such as asynchronous/synchronous or enabled/disabled), and documents that reference files that do not exist.
- **Facts Read from the Repository:** Identifies contributors to each module, single-owner modules, imports between modules, TODO/FIXME/HACK notes, undocumented configuration, modules without tests, and open issues.
- **Departure Simulator:** Select a person to see the modules only they know and generate an exit interview with one question per knowledge gap. Answers become evidence and move a Missing item to Uncertain, not directly to Verified.
- **Human Review:** Reviewers can approve, reject, edit, or resolve a conflict with a written reason. Conflicts cannot be approved while unresolved.
- **Role-Based Handover:** Supports published versions with history. Managers, developers, and new team members can receive different reports.
- **Permissions:** Supports JWT sign-in, project membership, roles, and managers-only sources.

## Run It Locally

### Requirements

- Python 3.11+
- Node.js 18+

### Installation and Startup

From the project root:

```bash
cd frontend
npm install
npm run build
cd ..

cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

Open [http://localhost:8000](http://localhost:8000) and choose a demo role.

The demo project is created on first start.

### Run Tests

From the project root:

```bash
cd backend
pip install pytest
python -m pytest -q
```

### Frontend Development

For frontend development, run the following commands in a separate terminal:

```bash
cd frontend
npm run dev
```

The frontend development server proxies `/api` requests to the backend on port 8000.

## Deployment

### Deploy Using One Docker Service

The `Dockerfile` builds the frontend and serves it from the API, allowing the application to run using a single URL.

1. Push this folder to a **public GitHub repository**.
2. On Render, select **New → Web Service**.
3. Connect the GitHub repository. Render should detect the Dockerfile.
4. Select the Free plan.
5. Configure the required environment variables using `.env.example`.
6. Open the deployed URL in a private browser window and test the application.

`SECRET_KEY` is required for secure authentication. `GITHUB_TOKEN` is useful for authenticated GitHub API access and higher API rate limits.

The application can also be deployed using Hugging Face Spaces with the Docker SDK.

### Deployment Notes

- Free hosting plans may sleep when idle, so the first request can take up to a minute.
- Without `DATABASE_URL`, SQLite data is stored inside the container and may be lost when the container restarts.
- The demo project is recreated on startup.

### Make Demo Evidence Links Clickable

The demo project uses a sample repository with a fictional team. To allow users to open its commits and files on GitHub:

```bash
python scripts/make_demo_repo.py payments-service-demo
cd payments-service-demo
git remote add origin https://github.com/YOUR_USER/payments-service-demo.git
git push -u origin main
```

Replace `YOUR_USER` with your GitHub username.

Then configure:

```env
DEMO_REPO=YOUR_USER/payments-service-demo
```

Restart the application after setting the variable.

## How a State Is Decided

| State | Rule |
|---|---|
| **Verified** | Counted or read directly from the repository, or stated in one source and supported by an independent source. |
| **Uncertain** | Stated in one place only, or supported only by indirect evidence such as age. |
| **Conflicting** | Two sources disagree. Only a reviewer can resolve the conflict with a written reason. |
| **Missing** | Something a successor needs, such as configuration, tests,