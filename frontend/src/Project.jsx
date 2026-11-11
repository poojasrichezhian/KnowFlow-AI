import React, { useCallback, useEffect, useState } from "react";
import { api, ROLE_NAME } from "./api.js";

const STATES = ["conflicting", "missing", "uncertain", "verified"];
const STATE_NAME = { verified: "Verified", uncertain: "Uncertain", conflicting: "Conflicting", missing: "Missing" };
const CATEGORY_NAME = { ownership: "Ownership", architecture: "Architecture", decision: "Decision", task: "Task", risk: "Risk", config: "Configuration", doc: "Documentation" };
const RELATION = { states: "Stated in", supports: "Supported by", contradicts: "Contradicted by", context: "Context from", testimony: "Explained in" };
const SOURCE_KIND = { github: "Repository", notes: "Notes", document: "Document", tasks: "Task list", interview: "Exit interviews" };

const date = (iso) => (iso ? new Date(iso + (iso.endsWith("Z") ? "" : "Z")).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "");

function useAction(after) {
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const run = async (label, call) => {
    setBusy(label);
    setError("");
    try {
      const out = await call();
      if (after) await after();
      setBusy("");
      return out;
    } catch (e) {
      setError(e.message);
      setBusy("");
      return undefined;
    }
  };
  return { busy, error, run, setError };
}

function Evidence({ items }) {
  return (
    <div className="evidence">
      {items.map((e, i) => (
        <div key={i} className={"ev " + e.relation}>
          <div className="where">
            <b>{RELATION[e.relation] || e.relation}</b>
            <span>{e.source}</span>
            {e.url ? <a href={e.url} target="_blank" rel="noreferrer" className="mono">{e.locator}</a> : <span className="mono">{e.locator}</span>}
            {e.kind === "computed" && <span className="tag plain">computed check</span>}
          </div>
          <div className="quote">{e.excerpt}</div>
        </div>
      ))}
    </div>
  );
}

function ClaimRow({ claim, canReview, onChanged, startOpen }) {
  const [open, setOpen] = useState(!!startOpen);
  const [mode, setMode] = useState("");
  const [text, setText] = useState(claim.text);
  const [note, setNote] = useState("");
  const { busy, error, run } = useAction(onChanged);
  const act = (action, extra = {}) =>
    run(action, () => api(`/claims/${claim.id}/review`, { method: "POST", body: { action, ...extra } })).then((ok) => ok && setMode(""));

  return (
    <div className="claim">
      <i className={"fill-" + claim.state} />
      <div className="claim-main">
        <button className="claim-head" onClick={() => setOpen(!open)} aria-expanded={open}>
          <span className={"tag " + claim.state}>{STATE_NAME[claim.state]}</span>
          <span className="text">{claim.text}</span>
          <span className="faint">{open ? "Hide" : `${claim.evidence.length} evidence`}</span>
        </button>
        <div className="why">{claim.why}</div>
        <div className="meta">
          <span className="tag plain">{CATEGORY_NAME[claim.category]}</span>
          {claim.module && <span className="tag plain mono">{claim.module}</span>}
          {claim.people.map((p) => <span key={p} className="tag plain">{p}</span>)}
          {claim.origin === "llm" && <span className="tag plain">found by LLM, quote checked</span>}
          {claim.edited && <span className="tag plain">edited by reviewer</span>}
          {canReview && claim.review_status !== "pending" && (
            <span className="tag plain">{claim.review_status} by {claim.reviewed_by}</span>
          )}
        </div>
        {open && (
          <>
            <Evidence items={claim.evidence} />
            {claim.review_note && <p className="faint" style={{ marginTop: 8 }}>Reviewer note: {claim.review_note}</p>}
            {error && <div className="error" role="alert" style={{ marginTop: 10 }}>{error}</div>}
            {canReview && mode === "" && (
              <div className="actions">
                {claim.review_status === "pending" && claim.state !== "conflicting" && (
                  <button className="btn small primary" disabled={!!busy} onClick={() => act("approve")}>
                    {claim.state === "verified" ? "Approve" : "Approve as a known " + (claim.state === "missing" ? "gap" : "uncertainty")}
                  </button>
                )}
                {claim.state === "conflicting" && <button className="btn small primary" onClick={() => setMode("resolve")}>Resolve conflict</button>}
                <button className="btn small" onClick={() => setMode("edit")}>Edit wording</button>
                {claim.review_status !== "rejected" && <button className="btn small danger" disabled={!!busy} onClick={() => act("reject")}>Reject</button>}
                {(claim.review_status !== "pending" || claim.state !== claim.engine_state) && (
                  <button className="btn small" disabled={!!busy} onClick={() => act("reopen")}>Reopen</button>
                )}
              </div>
            )}
            {mode === "edit" && (
              <div className="stack" style={{ marginTop: 12 }}>
                <label>Claim wording<textarea value={text} onChange={(e) => setText(e.target.value)} /></label>
                <div className="row">
                  <button className="btn small primary" disabled={!!busy} onClick={() => act("edit", { text })}>Save wording</button>
                  <button className="btn small" onClick={() => setMode("")}>Cancel</button>
                </div>
              </div>
            )}
            {mode === "resolve" && (
              <div className="resolve">
                <p>KnowFlow never picks a side. Say which source is right; your note is stored with the claim.</p>
                <label>Correct statement<textarea value={text} onChange={(e) => setText(e.target.value)} /></label>
                <label>Which source is right, and why<textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="The code is right. The notes describe a plan that was never built." /></label>
                <div className="row">
                  <button className="btn small primary" disabled={!!busy} onClick={() => act("resolve", { text, note })}>Resolve and approve</button>
                  <button className="btn small" onClick={() => setMode("")}>Cancel</button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function Readiness({ r }) {
  if (!r || !r.total) return null;
  return (
    <div className="panel readiness">
      <div>
        <div className="score">{r.score}<small>%</small></div>
        <div className="faint">handover readiness</div>
      </div>
      <div>
        <div className="bar" role="img" aria-label="Share of claims in each state">
          {STATES.slice().reverse().map((s) => <span key={s} className={"fill-" + s} style={{ width: `${(100 * (r.counts[s] || 0)) / r.total}%` }} />)}
        </div>
        <p className="faint" style={{ marginTop: 8 }}>
          {r.approved} of {r.total} claims reviewed. Verified and approved claims count in full, unreviewed or single-source claims count in part,
          open conflicts and gaps count for nothing.
        </p>
      </div>
    </div>
  );
}

function Review({ project, reload }) {
  const [claims, setClaims] = useState(null);
  const [state, setState] = useState("");
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("");
  const load = useCallback(() => api(`/projects/${project.id}/claims`).then(setClaims), [project.id]);
  useEffect(() => { load(); }, [load, project.analyzed_at]);
  const changed = async () => { await load(); await reload(); };
  const { busy, error, run } = useAction(changed);

  if (!claims) return <p className="muted">Loading claims…</p>;
  const shown = claims.filter((c) => (!state || c.state === state) && (!category || c.category === category) && (!status || c.review_status === status));
  const count = (s) => claims.filter((c) => c.state === s && c.review_status !== "rejected").length;
  const toApprove = claims.filter((c) => c.state === "verified" && c.review_status === "pending").length;

  return (
    <div className="stack" style={{ gap: 18 }}>
      <Readiness r={project.readiness} />
      {error && <div className="error" role="alert">{error}</div>}
      <div className="spread">
        <div className="legend" style={{ marginTop: 0 }}>
          <button className="chip" aria-pressed={state === ""} onClick={() => setState("")}>All {claims.length}</button>
          {STATES.map((s) => (
            <button key={s} className="chip" aria-pressed={state === s} onClick={() => setState(state === s ? "" : s)}>
              <span className={"dot fill-" + s} />{STATE_NAME[s]} {count(s)}
            </button>
          ))}
        </div>
        <div className="row">
          <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Filter by topic" style={{ width: "auto" }}>
            <option value="">All topics</option>
            {Object.entries(CATEGORY_NAME).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by review status" style={{ width: "auto" }}>
            <option value="">Any review status</option>
            <option value="pending">Waiting for review</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
          </select>
          {toApprove > 0 && (
            <button className="btn" disabled={!!busy} onClick={() => run("bulk", () => api(`/projects/${project.id}/approve-verified`, { method: "POST" }))}>
              Approve {toApprove} verified
            </button>
          )}
        </div>
      </div>
      <div className="ledger">
        {shown.length === 0 && (
          <div className="empty">
            {claims.length === 0 ? "No claims yet. Add a repository or a document under Sources." : "No claims match these filters."}
          </div>
        )}
        {shown.map((c) => <ClaimRow key={c.id + c.review_status + c.state + c.text} claim={c} canReview onChanged={changed} />)}
      </div>
    </div>
  );
}

function Departure({ project, reload }) {
  const [people, setPeople] = useState(null);
  const [person, setPerson] = useState("");
  const [data, setData] = useState(null);
  const [drafts, setDrafts] = useState({});
  const [error, setError] = useState("");
  const [saving, setSaving] = useState("");

  const loadPerson = useCallback((name) => api(`/projects/${project.id}/departure?person=${encodeURIComponent(name)}`).then(setData), [project.id]);
  useEffect(() => {
    api(`/projects/${project.id}/people`).then((list) => {
      setPeople(list);
      if (list.length) { setPerson(list[0].name); loadPerson(list[0].name); }
    }).catch((e) => setError(e.message));
  }, [project.id, loadPerson]);

  const pick = (name) => { setPerson(name); setData(null); loadPerson(name); };
  const save = async (q) => {
    setSaving(q.fingerprint);
    setError("");
    try {
      await api(`/projects/${project.id}/interview`, { method: "POST", body: { fingerprint: q.fingerprint, question: q.question, answer: drafts[q.fingerprint] || "", person } });
      setDrafts({ ...drafts, [q.fingerprint]: undefined });
      await Promise.all([loadPerson(person), api(`/projects/${project.id}/people`).then(setPeople), reload()]);
    } catch (e) {
      setError(e.message);
    }
    setSaving("");
  };

  if (error && !people) return <div className="error">{error}</div>;
  if (!people) return <p className="muted">Working out who knows what…</p>;
  if (!people.length) return <div className="panel empty">Connect a repository or a task list first. People are found from commit authors and task assignees.</div>;

  return (
    <div className="split">
      <div className="people">
        <p className="faint" style={{ marginBottom: 4 }}>Pick the person who is leaving</p>
        {people.map((p) => (
          <button key={p.name} className="person" aria-pressed={p.name === person} onClick={() => pick(p.name)}>
            <b>{p.name}</b>
            <span className="faint">
              {p.sole_owner_of.length ? `Sole owner of ${p.sole_owner_of.length} module${p.sole_owner_of.length > 1 ? "s" : ""}` : "No sole ownership"}
              {`, ${p.open_questions} open question${p.open_questions === 1 ? "" : "s"}`}
            </span>
          </button>
        ))}
      </div>

      {!data ? <p className="muted">Loading…</p> : (
        <div className="stack" style={{ gap: 18 }}>
          <div className="panel stack">
            <h2>If {data.person} left tomorrow</h2>
            <p className="muted" style={{ maxWidth: "70ch" }}>
              {data.sole_owner_of.length
                ? `${data.sole_owner_of.length} module${data.sole_owner_of.length > 1 ? "s have" : " has"} no second person with real commit history, and `
                : "Every module they work on has another contributor, and "}
              {data.open_questions} question{data.open_questions === 1 ? "" : "s"} only they can answer {data.open_questions === 1 ? "is" : "are"} still open.
            </p>
            <div>
              {data.modules.map((m) => (
                <div key={m.module} className="share">
                  <span className="mono">{m.module}</span>
                  <div className="track"><span className={m.share >= 75 ? "sole" : ""} style={{ width: m.share + "%" }} /></div>
                  <span className="faint">{m.share}%</span>
                </div>
              ))}
              {data.modules.length === 0 && <p className="faint">No commits by this person in the connected repositories.</p>}
            </div>
            <p className="faint">Share of commits per module. Red means 75% or more: nobody else could take it over from history alone.</p>
            {data.tasks.length > 0 && (
              <div>
                <h3 style={{ marginBottom: 6 }}>Open work assigned to them</h3>
                {data.tasks.map((t) => <div key={t.title} className="row" style={{ padding: "3px 0" }}><span className={"tag " + t.state}>{STATE_NAME[t.state]}</span><span>{t.title}</span></div>)}
              </div>
            )}
          </div>

          <div className="panel">
            <h2>Exit interview</h2>
            <p className="muted" style={{ marginTop: 4, maxWidth: "70ch" }}>
              One question per gap, conflict or risk tied to {data.person.split(" ")[0]}. An answer is stored as evidence. It moves a missing item to
              uncertain, not to verified: one person's account still needs a second source or a reviewer.
            </p>
            {error && <div className="error" role="alert" style={{ marginTop: 10 }}>{error}</div>}
            {data.questions.length === 0 && <p className="empty">Nothing to ask. Every claim tied to this person is already verified.</p>}
            {data.questions.map((q) => (
              <div key={q.fingerprint} className="question">
                <div className="row"><span className={"tag " + q.state}>{STATE_NAME[q.state]}</span><span className="faint">{q.title}</span></div>
                <p>{q.question}</p>
                {q.answered && drafts[q.fingerprint] === undefined ? (
                  <div className="answer">
                    <div className="faint">Answer on record</div>
                    <div>{q.answer}</div>
                    <button className="btn link" style={{ marginTop: 6 }} onClick={() => setDrafts({ ...drafts, [q.fingerprint]: q.answer })}>Change answer</button>
                  </div>
                ) : (
                  <>
                    <textarea aria-label="Answer" value={drafts[q.fingerprint] || ""} onChange={(e) => setDrafts({ ...drafts, [q.fingerprint]: e.target.value })} placeholder={`${data.person.split(" ")[0]}'s answer`} />
                    <div><button className="btn small primary" disabled={saving === q.fingerprint || !(drafts[q.fingerprint] || "").trim()} onClick={() => save(q)}>{saving === q.fingerprint ? "Saving…" : "Save answer"}</button></div>
                  </>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Handover({ project, reload }) {
  const manager = project.role === "manager";
  const [view, setView] = useState(manager ? "manager" : project.role);
  const [number, setNumber] = useState(0);
  const [report, setReport] = useState(null);
  const [note, setNote] = useState("");
  const load = useCallback(
    () => api(`/projects/${project.id}/report?as_role=${view}&version=${number}`).then(setReport),
    [project.id, view, number]
  );
  useEffect(() => { load(); }, [load, project.versions.length]);
  const { busy, error, run } = useAction(async () => { setNumber(0); setNote(""); await reload(); });

  const download = async () => {
    const md = await api(`/projects/${project.id}/report.md?as_role=${view}&version=${number}`, { text: true });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([md], { type: "text/markdown" }));
    a.download = `handover-v${report.version.number}-${view}.md`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  if (!report) return <p className="muted">Loading the handover…</p>;
  const pending = project.readiness?.pending || 0;

  return (
    <div className="stack" style={{ gap: 20 }}>
      {manager && (
        <div className="panel stack">
          <h2>Publish a handover</h2>
          <p className="muted" style={{ maxWidth: "70ch" }}>
            Publishing saves the approved claims as a new version. Developers and new team members only ever see published versions.
            {pending > 0 && ` ${pending} claims are still waiting for review and will be left out.`}
          </p>
          {error && <div className="error" role="alert">{error}</div>}
          <div className="row">
            <input type="text" className="grow" style={{ width: "auto", flex: 1, minWidth: 220 }} value={note} onChange={(e) => setNote(e.target.value)} placeholder="What changed in this version (optional)" aria-label="Version note" />
            <button className="btn primary" disabled={!!busy} onClick={() => run("publish", () => api(`/projects/${project.id}/publish`, { method: "POST", body: { note } }))}>
              {busy ? "Publishing…" : `Publish version ${(project.versions[0]?.number || 0) + 1}`}
            </button>
          </div>
        </div>
      )}

      {!report.version ? (
        <div className="panel empty">No handover has been published yet.{manager ? " Approve some claims under Review, then publish." : " Ask the project manager to review and publish one."}</div>
      ) : (
        <div className="report">
          <div className="spread">
            <div>
              <h2>Handover for a {ROLE_NAME[report.view].toLowerCase()}</h2>
              <p className="faint">
                Version {report.version.number}, approved by {report.version.created_by} on {date(report.version.created_at)}.
                {manager && ` Readiness at the time: ${Math.round(report.version.score)}%.`}
                {report.version.left_out > 0 && ` ${report.version.left_out} claims were still under review and are not included.`}
              </p>
            </div>
            <div className="row">
              {manager && (
                <select value={view} onChange={(e) => setView(e.target.value)} aria-label="Preview as role" style={{ width: "auto" }}>
                  {Object.entries(ROLE_NAME).map(([k, v]) => <option key={k} value={k}>Preview as {v.toLowerCase()}</option>)}
                </select>
              )}
              <select value={number} onChange={(e) => setNumber(Number(e.target.value))} aria-label="Version" style={{ width: "auto" }}>
                <option value={0}>Latest version</option>
                {project.versions.map((v) => <option key={v.number} value={v.number}>Version {v.number}</option>)}
              </select>
              <button className="btn" onClick={download}>Download Markdown</button>
            </div>
          </div>
          {report.sections.length === 0 && <div className="panel empty" style={{ marginTop: 16 }}>This version has nothing approved for this role yet.</div>}
          {report.sections.map((s) => (
            <section key={s.title}>
              <h2>{s.title}</h2>
              <div className="ledger">{s.claims.map((c) => <ClaimRow key={c.fingerprint} claim={c} canReview={false} />)}</div>
            </section>
          ))}
        </div>
      )}

      {project.versions.length > 0 && (
        <div className="panel">
          <h2 style={{ marginBottom: 8 }}>Version history</h2>
          <div className="versions">
            {project.versions.map((v) => (
              <div key={v.number}>
                <span><b>Version {v.number}</b> <span className="muted">{v.note}</span></span>
                <span className="faint">{v.claims} claims, approved by {v.created_by}, {date(v.created_at)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Sources({ project, reload }) {
  const manager = project.role === "manager";
  const [repo, setRepo] = useState("");
  const [notes, setNotes] = useState({ name: "", text: "", visibility: "everyone" });
  const [file, setFile] = useState(null);
  const [fileVisibility, setFileVisibility] = useState("everyone");
  const { busy, error, run } = useAction(reload);
  const base = `/projects/${project.id}/sources`;

  const upload = () => {
    const form = new FormData();
    form.append("file", file);
    form.append("visibility", fileVisibility);
    run("upload", () => api(base + "/upload", { method: "POST", form })).then((ok) => ok && setFile(null));
  };

  return (
    <div className="stack" style={{ gap: 20 }}>
      {error && <div className="error" role="alert">{error}</div>}
      <div className="panel">
        <h2 style={{ marginBottom: 6 }}>Connected sources</h2>
        <div className="list">
          {project.sources.length === 0 && <p className="muted">Nothing connected yet.</p>}
          {project.sources.map((s) => (
            <div key={s.id}>
              <div>
                <div className="row"><b>{s.name}</b><span className="tag plain">{SOURCE_KIND[s.kind]}</span>{s.visibility === "managers" && <span className="tag missing">Managers only</span>}</div>
                <div className="faint">Added by {s.added_by || "the team"} on {date(s.created_at)}{s.meta?.fetched_at ? `, read ${s.meta.fetched_at}` : ""}</div>
              </div>
              {manager && (
                <div className="row">
                  {s.kind === "github" && s.meta?.fetched_at !== "bundled snapshot" && (
                    <button className="btn small" disabled={!!busy} onClick={() => run("sync" + s.id, () => api(base + "/github", { method: "POST", body: { repo: s.name } }))}>{busy === "sync" + s.id ? "Reading…" : "Read again"}</button>
                  )}
                  {s.kind !== "github" && s.kind !== "interview" && (
                    <button className="btn small" disabled={!!busy} onClick={() => run("vis" + s.id, () => api(`${base}/${s.id}`, { method: "PATCH", body: { visibility: s.visibility === "managers" ? "everyone" : "managers" } }))}>
                      {s.visibility === "managers" ? "Share with everyone" : "Restrict to managers"}
                    </button>
                  )}
                  <button className="btn small danger" disabled={!!busy} onClick={() => window.confirm(`Remove ${s.name}? Claims that rely on it will change.`) && run("del" + s.id, () => api(`${base}/${s.id}`, { method: "DELETE" }))}>Remove</button>
                </div>
              )}
            </div>
          ))}
        </div>
        <p className="faint" style={{ marginTop: 10 }}>
          Claims that rest on a managers-only source are hidden from developers and new team members, including in published handovers.
        </p>
      </div>

      <div className="cols">
        <div className="panel stack">
          <h3>Public GitHub repository</h3>
          <input type="text" value={repo} onChange={(e) => setRepo(e.target.value)} placeholder="owner/name" aria-label="Repository" />
          <div><button className="btn primary" disabled={!!busy || !repo.trim()} onClick={() => run("repo", () => api(base + "/github", { method: "POST", body: { repo } })).then((ok) => ok && setRepo(""))}>{busy === "repo" ? "Reading the repository…" : "Connect repository"}</button></div>
        </div>
        <div className="panel stack">
          <h3>Upload a file</h3>
          <p className="faint">PDF, DOCX, Markdown or text. A CSV with key, summary, status and assignee columns is read as a task list.</p>
          <input type="file" accept=".pdf,.docx,.md,.txt,.rst,.csv" onChange={(e) => setFile(e.target.files[0] || null)} aria-label="File" />
          <select value={fileVisibility} onChange={(e) => setFileVisibility(e.target.value)} aria-label="Who can see this file">
            <option value="everyone">Everyone on the project can see it</option>
            <option value="managers">Managers only</option>
          </select>
          <div><button className="btn primary" disabled={!!busy || !file} onClick={upload}>{busy === "upload" ? "Reading the file…" : "Upload file"}</button></div>
        </div>
        <div className="panel stack">
          <h3>Paste meeting notes</h3>
          <input type="text" value={notes.name} onChange={(e) => setNotes({ ...notes, name: e.target.value })} placeholder="Title, for example Sprint review 4 Nov" aria-label="Title" />
          <textarea value={notes.text} onChange={(e) => setNotes({ ...notes, text: e.target.value })} placeholder={"One statement per line works best, for example:\nDecision: we moved image uploads to S3 because local disk filled up.\nPriya owns the billing module."} aria-label="Notes" />
          <div><button className="btn primary" disabled={!!busy || !notes.text.trim()} onClick={() => run("notes", () => api(base + "/text", { method: "POST", body: notes })).then((ok) => ok && setNotes({ name: "", text: "", visibility: "everyone" }))}>{busy === "notes" ? "Checking the notes…" : "Add notes"}</button></div>
        </div>
      </div>
    </div>
  );
}

function Team({ project, reload }) {
  const [form, setForm] = useState({ email: "", role: "developer" });
  const { busy, error, run } = useAction(reload);
  return (
    <div className="stack" style={{ gap: 20, maxWidth: 720 }}>
      <div className="panel">
        <h2 style={{ marginBottom: 6 }}>People on this project</h2>
        <div className="list">
          {project.members.map((m) => (
            <div key={m.user_id}>
              <div><b>{m.name}</b> <span className="faint">{m.email}</span></div>
              <div className="row">
                <span className="tag plain">{ROLE_NAME[m.role]}</span>
                <button className="btn small danger" disabled={!!busy} onClick={() => run("rm", () => api(`/projects/${project.id}/members/${m.user_id}`, { method: "DELETE" }))}>Remove</button>
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="panel stack">
        <h3>Add someone</h3>
        <p className="faint">They need a KnowFlow account first. Managers review and publish. Developers read the developer handover and answer exit interviews. New team members read the onboarding handover.</p>
        {error && <div className="error" role="alert">{error}</div>}
        <div className="row">
          <input type="email" style={{ flex: 1, minWidth: 200, width: "auto" }} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="their@email.com" aria-label="Email" />
          <select style={{ width: "auto" }} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} aria-label="Role">
            {Object.entries(ROLE_NAME).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <button className="btn primary" disabled={!!busy || !form.email.trim()} onClick={() => run("add", () => api(`/projects/${project.id}/members`, { method: "POST", body: form })).then((ok) => ok && setForm({ email: "", role: "developer" }))}>Add to project</button>
        </div>
      </div>
    </div>
  );
}

const TABS = {
  manager: [["review", "Review claims"], ["departure", "Departure simulator"], ["handover", "Handover"], ["sources", "Sources"], ["team", "Team"]],
  developer: [["handover", "Handover"], ["departure", "Departure simulator"], ["sources", "Sources"]],
  newcomer: [["handover", "Handover"]],
};

export default function Project({ id, onBack, onSignOut }) {
  const [project, setProject] = useState(null);
  const [tab, setTab] = useState("");
  const [error, setError] = useState("");
  const [resetting, setResetting] = useState(false);

  const reload = useCallback(
    () => api(`/projects/${id}`).then((p) => { setProject(p); setTab((t) => t || TABS[p.role][0][0]); })
      .catch((e) => (e.status === 401 ? onSignOut() : setError(e.message))),
    [id, onSignOut]
  );
  useEffect(() => { reload(); }, [reload]);

  const resetDemo = async () => {
    if (!window.confirm("Put the demo project back to its starting state? Reviews and answers made here will be cleared.")) return;
    setResetting(true);
    try {
      const { id: fresh } = await api("/demo/reset", { method: "POST" });
      location.hash = "project-" + fresh;
      if (fresh === id) await reload();
    } catch (e) {
      setError(e.message);
    }
    setResetting(false);
  };

  if (error) return <div className="page stack"><div className="error" role="alert">{error}</div><div><button className="btn" onClick={onBack}>Back to projects</button></div></div>;
  if (!project) return <div className="page"><p className="muted">Loading the project…</p></div>;

  return (
    <div className="page">
      <div className="project-head">
        <button className="btn link" style={{ justifySelf: "start" }} onClick={onBack}>All projects</button>
        <div className="spread">
          <h1>{project.name}</h1>
          <div className="row">
            <span className="tag plain">You are: {ROLE_NAME[project.role]}</span>
            {project.is_demo && project.role === "manager" && <button className="btn small" disabled={resetting} onClick={resetDemo}>{resetting ? "Resetting…" : "Reset demo"}</button>}
          </div>
        </div>
        <p className="muted" style={{ maxWidth: "80ch" }}>{project.description}</p>
      </div>
      <div className="tabs" role="tablist">
        {TABS[project.role].map(([key, label]) => <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}>{label}</button>)}
      </div>
      {tab === "review" && <Review project={project} reload={reload} />}
      {tab === "departure" && <Departure project={project} reload={reload} />}
      {tab === "handover" && <Handover project={project} reload={reload} />}
      {tab === "sources" && <Sources project={project} reload={reload} />}
      {tab === "team" && <Team project={project} reload={reload} />}
    </div>
  );
}
