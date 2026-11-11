import React, { useEffect, useState } from "react";
import { api, loadSession, saveSession, setToken, ROLE_NAME } from "./api.js";
import Project from "./Project.jsx";

const Logo = () => (
  <svg width="24" height="24" viewBox="0 0 32 32" aria-hidden="true">
    <rect width="32" height="32" rx="7" fill="#2747d6" />
    <path d="M9 16.5l4.5 4.5L23 11" stroke="#fff" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

function SignIn({ onSession }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  const run = async (label, call) => {
    setBusy(label);
    setError("");
    try {
      onSession(await call());
    } catch (e) {
      setError(e.message);
    }
    setBusy("");
  };
  const submit = (e) => {
    e.preventDefault();
    run("form", () => api(mode === "login" ? "/auth/login" : "/auth/signup", { method: "POST", body: form }));
  };
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  return (
    <div className="signin">
      <div className="pitch">
        <div className="brand" style={{ cursor: "default" }}><Logo /> KnowFlow AI</div>
        <h1>When someone leaves, find out what only they knew.</h1>
        <p>
          KnowFlow reads a project's repository, notes and task list, and checks every statement against the others.
          Each claim in the handover shows its evidence and one of four states. A person approves it before anyone else sees it.
        </p>
        <div className="sample" aria-label="Example claims">
          <div><i className="fill-verified" /><span>Arjun Sharma made 3 of 3 commits to webhooks/</span><span className="tag verified">Verified</span></div>
          <div><i className="fill-conflicting" /><span>Notes say retries are asynchronous; retry.py says synchronous</span><span className="tag conflicting">Conflicting</span></div>
          <div><i className="fill-uncertain" /><span>Rotate the webhook secret every 90 days</span><span className="tag uncertain">Uncertain</span></div>
          <div><i className="fill-missing" /><span>WEBHOOK_SECRET is not documented anywhere</span><span className="tag missing">Missing</span></div>
        </div>
      </div>

      <div className="form">
        <div className="stack">
          <h2>Open the demo project</h2>
          <p className="muted">No account needed. Each role sees a different handover.</p>
          <div className="demo-roles">
            {Object.entries(ROLE_NAME).map(([role, label]) => (
              <button key={role} className="btn" disabled={!!busy} onClick={() => run(role, () => api("/auth/demo/" + role, { method: "POST" }))}>
                <span>{busy === role ? "Opening…" : "Continue as " + label.toLowerCase()}</span>
                <span className="faint">{role === "manager" ? "reviews and approves" : role === "developer" ? "reads, answers questions" : "reads the approved handover"}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="divider">or use your own account</div>

        <form className="stack" onSubmit={submit}>
          {mode === "signup" && <label>Name<input type="text" value={form.name} onChange={set("name")} autoComplete="name" /></label>}
          <label>Email<input type="email" value={form.email} onChange={set("email")} autoComplete="email" /></label>
          <label>Password<input type="password" value={form.password} onChange={set("password")} autoComplete={mode === "login" ? "current-password" : "new-password"} /></label>
          {error && <div className="error" role="alert">{error}</div>}
          <div className="row">
            <button className="btn primary" disabled={!!busy}>{mode === "login" ? "Sign in" : "Create account"}</button>
            <button type="button" className="btn link" onClick={() => { setMode(mode === "login" ? "signup" : "login"); setError(""); }}>
              {mode === "login" ? "Create an account" : "I already have an account"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function Projects({ onOpen }) {
  const [projects, setProjects] = useState(null);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ name: "", repo: "" });
  const [busy, setBusy] = useState(false);

  const load = () => api("/projects").then(setProjects).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { id } = await api("/projects", { method: "POST", body: form });
      onOpen(id);
    } catch (err) {
      setError(err.message);
    }
    setBusy(false);
  };

  return (
    <div className="page stack" style={{ gap: 28 }}>
      <div className="stack" style={{ gap: 6 }}>
        <h1>Projects</h1>
        <p className="muted">Open a project to review its claims, or connect a new repository.</p>
      </div>
      {error && <div className="error" role="alert">{error}</div>}
      <div className="cards">
        {projects === null && <p className="muted">Loading projects…</p>}
        {projects?.map((p) => (
          <button key={p.id} className="card" onClick={() => onOpen(p.id)}>
            <div className="spread"><h2>{p.name}</h2><span className="tag plain">{ROLE_NAME[p.role]}</span></div>
            <p className="muted" style={{ fontSize: 14 }}>{p.description || "No description."}</p>
            <p className="faint">
              {p.readiness ? `Readiness ${p.readiness.score}%, ${p.readiness.pending} claims waiting for review. ` : ""}
              {p.version ? `Handover version ${p.version} published.` : "No handover published yet."}
            </p>
          </button>
        ))}
      </div>

      <form className="panel stack" onSubmit={create} style={{ maxWidth: 620 }}>
        <h2>Start a project from a public GitHub repository</h2>
        <p className="muted">KnowFlow reads commit history, code comments, imports, documents and open issues. You can add notes and files afterwards.</p>
        <label>Project name<input type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Billing service" /></label>
        <label>Repository<input type="text" value={form.repo} onChange={(e) => setForm({ ...form, repo: e.target.value })} placeholder="owner/name or https://github.com/owner/name" /></label>
        <div><button className="btn primary" disabled={busy}>{busy ? "Reading the repository…" : "Create project"}</button></div>
      </form>
    </div>
  );
}

export default function App() {
  const [session, setSession] = useState(loadSession);
  const [projectId, setProjectId] = useState(() => Number(location.hash.replace("#project-", "")) || null);

  useEffect(() => {
    const onHash = () => setProjectId(Number(location.hash.replace("#project-", "")) || null);
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const open = (id) => { location.hash = id ? "project-" + id : ""; setProjectId(id); };
  const start = (s) => { setToken(s.token); saveSession(s); setSession(s); };
  const signOut = () => { setToken(null); saveSession(null); setSession(null); open(null); };

  if (!session) return <SignIn onSession={start} />;
  return (
    <>
      <header className="topbar">
        <button className="brand" onClick={() => open(null)}><Logo /> KnowFlow AI</button>
        <div className="row">
          <span className="who">{session.user.name}</span>
          <button className="btn small" onClick={signOut}>Sign out</button>
        </div>
      </header>
      {projectId ? <Project key={projectId} id={projectId} onBack={() => open(null)} onSignOut={signOut} /> : <Projects onOpen={open} />}
    </>
  );
}
