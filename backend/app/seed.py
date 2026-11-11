"""Demo accounts and the bundled demo project, so the product is usable the moment it loads."""
import glob
import json
import os

from .auth import hash_password
from .db import Claim, Membership, Project, Source, User, Version, now

SEED = os.path.join(os.path.dirname(__file__), "..", "seed")
PLACEHOLDER = "DEMO_OWNER/payments-service-demo"
DEMO_USERS = {
    "manager": ("pm@knowflow.demo", "Divya Menon"),
    "developer": ("dev@knowflow.demo", "Karthik Raj"),
    "newcomer": ("new@knowflow.demo", "Ananya Das"),
}


def seed_demo(db, force=False):
    from .main import claim_dict, reanalyze
    from . import engine

    users = {}
    for role, (email, name) in DEMO_USERS.items():
        u = db.query(User).filter_by(email=email).first()
        if not u:
            u = User(email=email, name=name, pw_hash=hash_password(os.urandom(12).hex()))
            db.add(u)
            db.flush()
        users[role] = u
    db.commit()

    demo = db.query(Project).filter_by(is_demo=1).first()
    if demo and not force:
        return demo.id
    if demo:
        for model in (Claim, Source, Version, Membership):
            db.query(model).filter_by(project_id=demo.id).delete()
        db.delete(demo)
        db.commit()

    p = Project(name="Payments Service (demo)", is_demo=1, created_by=users["manager"].id,
                description="Arjun Sharma, the senior backend developer, leaves on 14 Nov 2026. "
                            "A sample repository, two sets of notes and a task export are connected.")
    db.add(p)
    db.flush()
    for role, u in users.items():
        db.add(Membership(user_id=u.id, project_id=p.id, role=role))

    raw = open(os.path.join(SEED, "demo_snapshot.json"), encoding="utf-8").read()
    repo = os.environ.get("DEMO_REPO", "").strip()
    snap = json.loads(raw.replace(PLACEHOLDER, repo) if repo else raw)
    if not repo:
        snap["repo"], snap["no_links"] = "payments-service-demo", True  # no public copy configured: show excerpts without links
    db.add(Source(project_id=p.id, kind="github", name=snap["repo"], content=json.dumps(snap),
                  meta={"fetched_at": snap["fetched_at"]}, added_by="Divya Menon"))
    for path in sorted(glob.glob(os.path.join(SEED, "docs", "*"))):
        name = os.path.basename(path)
        db.add(Source(project_id=p.id, kind="tasks" if name.endswith(".csv") else "notes", name=name,
                      content=open(path, encoding="utf-8").read(), added_by="Divya Menon",
                      visibility="managers" if "vendor" in name else "everyone"))
    db.commit()
    reanalyze(db, p)

    # A first handover is already published so the developer and newcomer accounts have something to read.
    # Conflicts, gaps and single-source claims are left for the reviewer.
    for c in db.query(Claim).filter_by(project_id=p.id, state="verified"):
        c.review_status, c.reviewed_by, c.reviewed_at = "approved", "Divya Menon", now()
    db.commit()
    claims = [claim_dict(c) for c in db.query(Claim).filter_by(project_id=p.id)]
    approved = [c for c in claims if c["review_status"] == "approved"]
    db.add(Version(project_id=p.id, number=1, score=engine.readiness(claims)["score"], created_by="Divya Menon",
                   note="First pass: everything the verifier could back with evidence.",
                   payload={"claims": approved, "left_out": len(claims) - len(approved)}))
    db.commit()
    return p.id
