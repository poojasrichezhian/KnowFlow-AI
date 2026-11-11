"""KnowFlow AI API."""
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import engine, llm
from .auth import ROLES, check_password, current_user, get_db, hash_password, make_token, role_in
from .db import Claim, Membership, Project, SessionLocal, Source, User, Version, init_db, now
from .docs_ingest import extract
from .github_ingest import GitHubError, fetch_snapshot



@asynccontextmanager
async def lifespan(_app):
    from .seed import seed_demo
    init_db()
    db = SessionLocal()
    try:
        seed_demo(db)
    finally:
        db.close()
    yield


app = FastAPI(title="KnowFlow AI", lifespan=lifespan)

WRITERS = ("manager", "developer")
MANAGER = ("manager",)


# ----------------------------------------------------------------------------- helpers

def source_dict(s):
    return {"id": s.id, "kind": s.kind, "name": s.name, "visibility": s.visibility, "content": s.content, "meta": s.meta or {}}


def claim_dict(c):
    return {
        "id": c.id, "fingerprint": c.fingerprint, "category": c.category, "title": c.title,
        "text": c.edited_text or c.text, "edited": bool(c.edited_text), "state": c.state, "engine_state": c.engine_state,
        "why": c.why, "origin": c.origin, "origin_source": c.origin_source, "module": c.module, "people": c.people or [],
        "evidence": c.evidence or [], "review_status": c.review_status, "review_note": c.review_note or "",
        "reviewed_by": c.reviewed_by or "", "reviewed_at": c.reviewed_at.isoformat() if c.reviewed_at else None,
        "answered": any(e["relation"] == "testimony" for e in (c.evidence or [])),
    }


def visible(claims, restricted):
    """Source-level permissions: drop anything that rests on a source the viewer may not see."""
    out = []
    for c in claims:
        if c.get("origin_source") in restricted:
            continue
        evidence = [e for e in c["evidence"] if e["source_id"] not in restricted]
        if evidence:
            out.append(dict(c, evidence=evidence))
    return out


def restricted_ids(db, project_id, role):
    if role == "manager":
        return set()
    return {s.id for s in db.query(Source).filter_by(project_id=project_id, visibility="managers")}


def reanalyze(db, project):
    """Run the verifier and store the result, keeping review decisions for claims that did not change."""
    sources = db.query(Source).filter_by(project_id=project.id).order_by(Source.id).all()
    claims, facts = engine.analyze([source_dict(s) for s in sources])
    old = {c.fingerprint: c for c in db.query(Claim).filter_by(project_id=project.id)}
    db.query(Claim).filter_by(project_id=project.id).delete()
    for c in claims:
        row = Claim(project_id=project.id, fingerprint=c["fingerprint"], category=c["category"], title=c["title"],
                    text=c["text"], engine_state=c["state"], state=c["state"], why=c["why"], origin=c["origin"],
                    origin_source=c["origin_source"], module=c["module"], people=c["people"], evidence=c["evidence"])
        prev = old.get(c["fingerprint"])
        if prev and prev.engine_state == c["state"] and prev.text == c["text"]:
            row.review_status, row.edited_text, row.review_note = prev.review_status, prev.edited_text, prev.review_note
            row.reviewed_by, row.reviewed_at, row.state = prev.reviewed_by, prev.reviewed_at, prev.state
            if prev.state != prev.engine_state:
                row.why = prev.why
        db.add(row)
    project.analyzed_at = now()
    db.commit()
    return facts


def project_claims(db, project_id):
    order = {"conflicting": 0, "missing": 1, "uncertain": 2, "verified": 3}
    rows = [claim_dict(c) for c in db.query(Claim).filter_by(project_id=project_id)]
    rows.sort(key=lambda c: (order[c["state"]], engine.CATEGORIES.index(c["category"]), c["title"]))
    return rows


def facts_for(db, project_id):
    sources = db.query(Source).filter_by(project_id=project_id).order_by(Source.id).all()
    return engine.analyze([source_dict(s) for s in sources])[1]


REPORT = {
    "manager": [("Needs your decision", lambda c: c["state"] == "conflicting"),
                ("Known gaps", lambda c: c["state"] == "missing"),
                ("Risks", lambda c: c["category"] == "risk"), ("Who owns what", lambda c: c["category"] == "ownership"),
                ("Pending work", lambda c: c["category"] == "task"), ("Decisions", lambda c: c["category"] == "decision"),
                ("How the parts fit together", lambda c: c["category"] == "architecture"),
                ("Configuration", lambda c: c["category"] == "config"), ("Documentation", lambda c: c["category"] == "doc")],
    "developer": [("How the parts fit together", lambda c: c["category"] == "architecture"),
                  ("Decisions and why", lambda c: c["category"] == "decision"),
                  ("Pending work", lambda c: c["category"] == "task"), ("Risks in the code", lambda c: c["category"] == "risk"),
                  ("Configuration", lambda c: c["category"] == "config"),
                  ("Who owns what", lambda c: c["category"] == "ownership"),
                  ("Documentation you cannot trust yet", lambda c: c["category"] == "doc")],
    "newcomer": [("Who to ask", lambda c: c["category"] == "ownership" and c["state"] == "verified"),
                 ("How the parts fit together", lambda c: c["category"] == "architecture" and c["state"] == "verified"),
                 ("What you need to run it", lambda c: c["category"] == "config" and c["state"] == "verified"),
                 ("Decisions already made", lambda c: c["category"] == "decision" and c["state"] == "verified"),
                 ("Watch out for", lambda c: c["category"] == "risk" and c["state"] == "verified")],
}


def build_report(claims, role):
    used, sections = set(), []
    for title, pick in REPORT[role]:
        items = [c for c in claims if c["fingerprint"] not in used and pick(c)]
        used.update(c["fingerprint"] for c in items)
        if items:
            sections.append({"title": title, "claims": items})
    return sections


def report_markdown(project, version, role, sections):
    out = [f"# {project.name}: handover for a {role}", "",
           f"Version {version.number}, approved by {version.created_by} on {version.created_at:%d %b %Y}. "
           f"Readiness {round(version.score)}%.", ""]
    for s in sections:
        out += [f"## {s['title']}", ""]
        for c in s["claims"]:
            out.append(f"- **[{c['state'].upper()}]** {c['text']}")
            for e in c["evidence"]:
                where = f"[{e['locator']}]({e['url']})" if e.get("url") else e["locator"]
                out.append(f"  - {e['relation']}: {e['source']}, {where}: “{e['excerpt']}”")
        out.append("")
    return "\n".join(out)


# ----------------------------------------------------------------------------- auth

class SignUp(BaseModel):
    email: str
    name: str
    password: str


class Login(BaseModel):
    email: str
    password: str


def session(user):
    return {"token": make_token(user), "user": {"id": user.id, "name": user.name, "email": user.email}}


@app.post("/api/auth/signup")
def signup(body: SignUp, db=Depends(get_db)):
    email = body.email.strip().lower()
    if "@" not in email or len(body.password) < 6 or not body.name.strip():
        raise HTTPException(400, "Enter a name, a valid email and a password of at least 6 characters.")
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(400, "An account with this email already exists. Sign in instead.")
    user = User(email=email, name=body.name.strip(), pw_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    return session(user)


@app.post("/api/auth/login")
def login(body: Login, db=Depends(get_db)):
    user = db.query(User).filter_by(email=body.email.strip().lower()).first()
    if not user or not check_password(body.password, user.pw_hash):
        raise HTTPException(401, "Email or password is wrong.")
    return session(user)


@app.post("/api/auth/demo/{role}")
def demo_login(role: str, db=Depends(get_db)):
    from .seed import DEMO_USERS
    if role not in DEMO_USERS:
        raise HTTPException(404, "No such demo account.")
    user = db.query(User).filter_by(email=DEMO_USERS[role][0]).first()
    return session(user)


@app.get("/api/me")
def me(user=Depends(current_user)):
    return {"id": user.id, "name": user.name, "email": user.email}


# ----------------------------------------------------------------------------- projects

class NewProject(BaseModel):
    name: str
    description: str = ""
    repo: str = ""


@app.get("/api/projects")
def list_projects(user=Depends(current_user), db=Depends(get_db)):
    out = []
    for m in db.query(Membership).filter_by(user_id=user.id):
        p = db.get(Project, m.project_id)
        r = engine.readiness([claim_dict(c) for c in db.query(Claim).filter_by(project_id=p.id)])
        latest = db.query(Version).filter_by(project_id=p.id).order_by(Version.number.desc()).first()
        out.append({"id": p.id, "name": p.name, "description": p.description, "role": m.role, "is_demo": bool(p.is_demo),
                    "readiness": r if m.role == "manager" else None, "version": latest.number if latest else None})
    return out


@app.post("/api/projects")
def create_project(body: NewProject, user=Depends(current_user), db=Depends(get_db)):
    if not body.name.strip():
        raise HTTPException(400, "Give the project a name.")
    snap = None
    if body.repo.strip():
        try:
            snap = fetch_snapshot(body.repo)
        except GitHubError as e:
            raise HTTPException(400, str(e))
    p = Project(name=body.name.strip(), description=body.description.strip() or (snap or {}).get("description", ""), created_by=user.id)
    db.add(p)
    db.flush()
    db.add(Membership(user_id=user.id, project_id=p.id, role="manager"))
    if snap:
        db.add(Source(project_id=p.id, kind="github", name=snap["repo"], content=json.dumps(snap),
                      meta={"fetched_at": snap["fetched_at"]}, added_by=user.name))
    db.commit()
    reanalyze(db, p)
    return {"id": p.id}


@app.get("/api/projects/{pid}")
def get_project(pid: int, user=Depends(current_user), db=Depends(get_db)):
    role = role_in(db, user, pid)
    p = db.get(Project, pid)
    hidden = restricted_ids(db, pid, role)
    sources = [{"id": s.id, "kind": s.kind, "name": s.name, "visibility": s.visibility, "added_by": s.added_by,
                "created_at": s.created_at.isoformat(), "meta": {k: v for k, v in (s.meta or {}).items() if k != "llm_claims"},
                "size": len(s.content or "")}
               for s in db.query(Source).filter_by(project_id=pid).order_by(Source.id) if s.id not in hidden]
    members = []
    for m in db.query(Membership).filter_by(project_id=pid):
        u = db.get(User, m.user_id)
        members.append({"user_id": u.id, "name": u.name, "email": u.email, "role": m.role})
    versions = [{"number": v.number, "score": v.score, "created_by": v.created_by, "created_at": v.created_at.isoformat(),
                 "note": v.note, "claims": len(v.payload.get("claims", []))}
                for v in db.query(Version).filter_by(project_id=pid).order_by(Version.number.desc())]
    claims = project_claims(db, pid)
    return {"id": p.id, "name": p.name, "description": p.description, "is_demo": bool(p.is_demo), "role": role,
            "analyzed_at": p.analyzed_at.isoformat() if p.analyzed_at else None, "sources": sources, "members": members,
            "versions": versions, "readiness": engine.readiness(claims) if role == "manager" else None,
            "llm": llm.enabled()}


@app.delete("/api/projects/{pid}")
def delete_project(pid: int, user=Depends(current_user), db=Depends(get_db)):
    role_in(db, user, pid, MANAGER)
    p = db.get(Project, pid)
    if p.is_demo:
        raise HTTPException(400, "The demo project cannot be deleted. Use Reset demo instead.")
    for model in (Claim, Source, Version, Membership):
        db.query(model).filter_by(project_id=pid).delete()
    db.delete(p)
    db.commit()
    return {"ok": True}


# ----------------------------------------------------------------------------- sources

class RepoIn(BaseModel):
    repo: str


class TextIn(BaseModel):
    name: str
    text: str
    visibility: str = "everyone"


def add_document(db, project, user, name, kind, text, visibility):
    if not text.strip():
        raise HTTPException(400, "This file has no readable text.")
    if visibility not in ("everyone", "managers"):
        visibility = "everyone"
    meta = {}
    if kind != "tasks":
        found = llm.extract_claims(text)
        if found:
            meta["llm_claims"] = found
    db.add(Source(project_id=project.id, kind=kind, name=name[:300], content=text[:400_000], visibility=visibility,
                  meta=meta, added_by=user.name))
    db.commit()
    reanalyze(db, project)


@app.post("/api/projects/{pid}/sources/github")
def add_repo(pid: int, body: RepoIn, user=Depends(current_user), db=Depends(get_db)):
    role_in(db, user, pid, WRITERS)
    try:
        snap = fetch_snapshot(body.repo)
    except GitHubError as e:
        raise HTTPException(400, str(e))
    existing = db.query(Source).filter_by(project_id=pid, kind="github", name=snap["repo"]).first()
    if existing:
        existing.content, existing.meta = json.dumps(snap), {"fetched_at": snap["fetched_at"]}
    else:
        db.add(Source(project_id=pid, kind="github", name=snap["repo"], content=json.dumps(snap),
                      meta={"fetched_at": snap["fetched_at"]}, added_by=user.name))
    db.commit()
    reanalyze(db, db.get(Project, pid))
    return {"ok": True}


@app.post("/api/projects/{pid}/sources/text")
def add_text(pid: int, body: TextIn, user=Depends(current_user), db=Depends(get_db)):
    role_in(db, user, pid, WRITERS)
    add_document(db, db.get(Project, pid), user, body.name.strip() or "Pasted notes", "notes", body.text, body.visibility)
    return {"ok": True}


@app.post("/api/projects/{pid}/sources/upload")
async def upload(pid: int, file: UploadFile = File(...), visibility: str = Form("everyone"),
                 user=Depends(current_user), db=Depends(get_db)):
    role_in(db, user, pid, WRITERS)
    data = await file.read()
    if len(data) > 5_000_000:
        raise HTTPException(400, "Files up to 5 MB are supported.")
    try:
        kind, text = extract(file.filename or "upload", data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:
        raise HTTPException(400, "This file could not be read. Check that it is not password-protected or damaged.")
    add_document(db, db.get(Project, pid), user, file.filename or "upload", kind, text, visibility)
    return {"ok": True}


class VisibilityIn(BaseModel):
    visibility: str


@app.patch("/api/projects/{pid}/sources/{sid}")
def set_visibility(pid: int, sid: int, body: VisibilityIn, user=Depends(current_user), db=Depends(get_db)):
    role_in(db, user, pid, MANAGER)
    s = db.query(Source).filter_by(id=sid, project_id=pid).first()
    if not s or body.visibility not in ("everyone", "managers"):
        raise HTTPException(404, "Source not found.")
    s.visibility = body.visibility
    db.commit()
    return {"ok": True}


@app.delete("/api/projects/{pid}/sources/{sid}")
def delete_source(pid: int, sid: int, user=Depends(current_user), db=Depends(get_db)):
    role_in(db, user, pid, MANAGER)
    s = db.query(Source).filter_by(id=sid, project_id=pid).first()
    if not s:
        raise HTTPException(404, "Source not found.")
    db.delete(s)
    db.commit()
    reanalyze(db, db.get(Project, pid))
    return {"ok": True}


@app.post("/api/projects/{pid}/analyze")
def analyze_now(pid: int, user=Depends(current_user), db=Depends(get_db)):
    role_in(db, user, pid, WRITERS)
    reanalyze(db, db.get(Project, pid))
    return {"ok": True}


# ----------------------------------------------------------------------------- claims and review

@app.get("/api/projects/{pid}/claims")
def get_claims(pid: int, user=Depends(current_user), db=Depends(get_db)):
    role_in(db, user, pid, MANAGER)  # nothing is shared before approval: others read the published handover
    return project_claims(db, pid)


class Review(BaseModel):
    action: str  # approve | reject | reopen | edit | resolve
    text: str = ""
    note: str = ""


@app.post("/api/claims/{cid}/review")
def review(cid: int, body: Review, user=Depends(current_user), db=Depends(get_db)):
    c = db.get(Claim, cid)
    if not c:
        raise HTTPException(404, "This claim no longer exists. Reload the page.")
    role_in(db, user, c.project_id, MANAGER)
    if body.action == "approve":
        if c.state == "conflicting":
            raise HTTPException(400, "Resolve the conflict first: say which source is right.")
        c.review_status = "approved"
    elif body.action == "reject":
        c.review_status = "rejected"
    elif body.action == "reopen":
        c.review_status, c.state, c.edited_text = "pending", c.engine_state, None
    elif body.action == "edit":
        if not body.text.strip():
            raise HTTPException(400, "The claim text cannot be empty.")
        c.edited_text = body.text.strip()
    elif body.action == "resolve":
        if c.state != "conflicting" or not body.note.strip():
            raise HTTPException(400, "Write which source is right and why. The note is kept with the claim.")
        c.state, c.review_status = "verified", "approved"
        if body.text.strip():
            c.edited_text = body.text.strip()
        c.why = f"Sources disagreed. Resolved by {user.name}: {body.note.strip()}"
    else:
        raise HTTPException(400, "Unknown action.")
    if body.note.strip():
        c.review_note = body.note.strip()
    c.reviewed_by, c.reviewed_at = user.name, now()
    db.commit()
    return claim_dict(c)


@app.post("/api/projects/{pid}/approve-verified")
def approve_verified(pid: int, user=Depends(current_user), db=Depends(get_db)):
    role_in(db, user, pid, MANAGER)
    n = 0
    for c in db.query(Claim).filter_by(project_id=pid, state="verified", review_status="pending"):
        c.review_status, c.reviewed_by, c.reviewed_at = "approved", user.name, now()
        n += 1
    db.commit()
    return {"approved": n}


# ----------------------------------------------------------------------------- departure simulator

@app.get("/api/projects/{pid}/people")
def people(pid: int, user=Depends(current_user), db=Depends(get_db)):
    role = role_in(db, user, pid, WRITERS)
    facts = facts_for(db, pid)
    claims = visible(project_claims(db, pid), restricted_ids(db, pid, role))
    out = []
    for person in facts["people"]:
        d = engine.departure(claims, facts, person)
        out.append({"name": person, "commits": sum(m["commits"] for m in d["modules"]), "sole_owner_of": d["sole_owner_of"],
                    "tasks": len(d["tasks"]), "questions": len(d["questions"]), "open_questions": d["open_questions"]})
    out.sort(key=lambda p: (-len(p["sole_owner_of"]), -p["open_questions"], -p["commits"]))
    return out


@app.get("/api/projects/{pid}/departure")
def departure(pid: int, person: str, user=Depends(current_user), db=Depends(get_db)):
    role = role_in(db, user, pid, WRITERS)
    claims = visible(project_claims(db, pid), restricted_ids(db, pid, role))
    return engine.departure(claims, facts_for(db, pid), person)


class Answer(BaseModel):
    fingerprint: str
    question: str
    answer: str
    person: str


@app.post("/api/projects/{pid}/interview")
def answer(pid: int, body: Answer, user=Depends(current_user), db=Depends(get_db)):
    role_in(db, user, pid, WRITERS)
    if len(body.answer.strip()) < 10:
        raise HTTPException(400, "Write a fuller answer. A successor will rely on it.")
    src = db.query(Source).filter_by(project_id=pid, kind="interview").first()
    if not src:
        src = Source(project_id=pid, kind="interview", name="Exit interviews", content="[]", added_by=user.name)
        db.add(src)
    items = [i for i in json.loads(src.content or "[]") if i["fingerprint"] != body.fingerprint]
    items.append({"fingerprint": body.fingerprint, "question": body.question, "answer": body.answer.strip(),
                  "person": body.person, "by": user.name, "at": datetime.now(timezone.utc).strftime("%Y-%m-%d")})
    src.content = json.dumps(items)
    db.commit()
    reanalyze(db, db.get(Project, pid))
    return {"ok": True}


# ----------------------------------------------------------------------------- handover: publish, versions, reports

class Publish(BaseModel):
    note: str = ""


@app.post("/api/projects/{pid}/publish")
def publish(pid: int, body: Publish, user=Depends(current_user), db=Depends(get_db)):
    role_in(db, user, pid, MANAGER)
    claims = project_claims(db, pid)
    approved = [c for c in claims if c["review_status"] == "approved"]
    if not approved:
        raise HTTPException(400, "Approve at least one claim before publishing a handover.")
    last = db.query(Version).filter_by(project_id=pid).order_by(Version.number.desc()).first()
    v = Version(project_id=pid, number=(last.number + 1) if last else 1, score=engine.readiness(claims)["score"],
                note=body.note.strip(), created_by=user.name,
                payload={"claims": approved, "left_out": len([c for c in claims if c["review_status"] == "pending"])})
    db.add(v)
    db.commit()
    return {"number": v.number}


def load_report(db, user, pid, as_role, number):
    role = role_in(db, user, pid)
    view = as_role if (role == "manager" and as_role in ROLES) else role
    q = db.query(Version).filter_by(project_id=pid)
    v = q.filter_by(number=number).first() if number else q.order_by(Version.number.desc()).first()
    if not v:
        return role, view, None, []
    hidden = restricted_ids(db, pid, view)
    return role, view, v, build_report(visible(v.payload.get("claims", []), hidden), view)


@app.get("/api/projects/{pid}/report")
def report(pid: int, as_role: str = "", version: int = 0, user=Depends(current_user), db=Depends(get_db)):
    role, view, v, sections = load_report(db, user, pid, as_role, version)
    if not v:
        return {"role": role, "view": view, "version": None, "sections": []}
    return {"role": role, "view": view, "sections": sections,
            "version": {"number": v.number, "score": v.score, "created_by": v.created_by,
                        "created_at": v.created_at.isoformat(), "note": v.note, "left_out": v.payload.get("left_out", 0)}}


@app.get("/api/projects/{pid}/report.md", response_class=PlainTextResponse)
def report_md(pid: int, as_role: str = "", version: int = 0, user=Depends(current_user), db=Depends(get_db)):
    role, view, v, sections = load_report(db, user, pid, as_role, version)
    if not v:
        raise HTTPException(404, "No handover has been published yet.")
    return report_markdown(db.get(Project, pid), v, view, sections)


# ----------------------------------------------------------------------------- members

class MemberIn(BaseModel):
    email: str
    role: str


@app.post("/api/projects/{pid}/members")
def add_member(pid: int, body: MemberIn, user=Depends(current_user), db=Depends(get_db)):
    role_in(db, user, pid, MANAGER)
    if body.role not in ROLES:
        raise HTTPException(400, "Role must be manager, developer or newcomer.")
    other = db.query(User).filter_by(email=body.email.strip().lower()).first()
    if not other:
        raise HTTPException(404, "Nobody has signed up with that email yet. Ask them to create an account first.")
    m = db.query(Membership).filter_by(user_id=other.id, project_id=pid).first()
    if m:
        if other.id == user.id:
            raise HTTPException(400, "You cannot change your own role.")
        m.role = body.role
    else:
        db.add(Membership(user_id=other.id, project_id=pid, role=body.role))
    db.commit()
    return {"ok": True}


@app.delete("/api/projects/{pid}/members/{uid}")
def remove_member(pid: int, uid: int, user=Depends(current_user), db=Depends(get_db)):
    role_in(db, user, pid, MANAGER)
    if uid == user.id:
        raise HTTPException(400, "You cannot remove yourself.")
    db.query(Membership).filter_by(user_id=uid, project_id=pid).delete()
    db.commit()
    return {"ok": True}


# ----------------------------------------------------------------------------- demo and static files

@app.post("/api/demo/reset")
def reset_demo(user=Depends(current_user), db=Depends(get_db)):
    from .seed import seed_demo
    demo = db.query(Project).filter_by(is_demo=1).first()
    if demo:
        role_in(db, user, demo.id, MANAGER)
    return {"id": seed_demo(db, force=True)}


@app.get("/api/health")
def health():
    return {"ok": True, "llm": llm.enabled(), "github_token": bool(os.environ.get("GITHUB_TOKEN"))}


DIST = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
if os.path.isdir(DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST, "assets")), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found.")
        root = os.path.realpath(DIST)
        target = os.path.realpath(os.path.join(root, path))
        inside = target.startswith(root + os.sep) and os.path.isfile(target)
        return FileResponse(target if inside else os.path.join(root, "index.html"))
