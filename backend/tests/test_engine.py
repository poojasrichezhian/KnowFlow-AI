"""Run with:  cd backend && python -m pytest -q"""
import glob
import json
import os

from app import llm
from app.engine import analyze, departure, doc_passages, polarity, readiness

SEED = os.path.join(os.path.dirname(__file__), "..", "seed")


def demo_sources(extra=()):
    snap = json.load(open(os.path.join(SEED, "demo_snapshot.json")))
    snap["no_links"] = True
    sources = [{"id": 1, "kind": "github", "name": "repo", "visibility": "everyone", "content": json.dumps(snap), "meta": {}}]
    for i, path in enumerate(sorted(glob.glob(os.path.join(SEED, "docs", "*"))), 2):
        kind = "tasks" if path.endswith(".csv") else "notes"
        sources.append({"id": i, "kind": kind, "name": os.path.basename(path), "visibility": "everyone",
                        "content": open(path).read(), "meta": {}})
    return sources + list(extra)


def find(claims, text):
    return next(c for c in claims if text.lower() in (c["title"] + " " + c["text"]).lower())


def test_every_claim_has_evidence_and_a_state():
    claims, _ = analyze(demo_sources())
    assert claims
    for c in claims:
        assert c["state"] in ("verified", "uncertain", "conflicting", "missing")
        assert c["evidence"], c["title"]
        assert c["why"]


def test_quoted_evidence_is_verbatim_in_its_source():
    sources = demo_sources()
    blob = {s["id"]: " ".join(s["content"].split()) for s in sources}
    snap = json.loads(sources[0]["content"])
    commits = [c["message"] for cs in snap["module_commits"].values() for c in cs] + [c["message"] for c in snap["readme_commits"]]
    blob[1] = " ".join(" ".join(list(snap["files"].values()) + commits).split())
    claims, _ = analyze(sources)
    checked = 0
    for c in claims:
        for e in c["evidence"]:
            if e["kind"] == "quote" and e["source_kind"] != "tasks":
                assert e["excerpt"] in blob[e["source_id"]], e
                checked += 1
    assert checked > 40


def test_notes_that_contradict_the_code_are_conflicting():
    claims, _ = analyze(demo_sources())
    c = find(claims, "moved to an asynchronous background queue")
    assert c["state"] == "conflicting"
    assert any(e["relation"] == "contradicts" and "retry.py" in e["locator"] for e in c["evidence"])


def test_ownership_claim_is_checked_against_commit_history():
    claims, _ = analyze(demo_sources())
    assert find(claims, "Rohan owns the webhooks module")["state"] == "conflicting"
    assert find(claims, "Meera is responsible for the auth module")["state"] == "verified"


def test_task_marked_done_in_notes_but_open_in_tracker_is_conflicting():
    claims, _ = analyze(demo_sources())
    assert find(claims, "refunds table migration is completed")["state"] == "conflicting"


def test_document_pointing_at_missing_file_is_conflicting():
    claims, _ = analyze(demo_sources())
    assert find(claims, "workers/retry_worker.py")["state"] == "conflicting"


def test_undocumented_env_var_is_missing_and_documented_one_is_verified():
    claims, _ = analyze(demo_sources())
    assert find(claims, "WEBHOOK_SECRET is not documented")["state"] == "missing"
    assert find(claims, "DATABASE_URL is needed")["state"] == "verified"


def test_single_source_statement_is_uncertain():
    claims, _ = analyze(demo_sources())
    assert find(claims, "rotate the webhook secret")["state"] == "uncertain"


def test_exit_interview_answer_moves_missing_to_uncertain_never_straight_to_verified():
    claims, _ = analyze(demo_sources())
    gap = find(claims, "WEBHOOK_SECRET is not documented")
    interview = {"id": 99, "kind": "interview", "name": "Exit interviews", "visibility": "everyone", "meta": {},
                 "content": json.dumps([{"fingerprint": gap["fingerprint"], "question": "?", "person": "Arjun Sharma",
                                         "answer": "It signs gateway webhooks. The value is in the gateway dashboard."}])}
    claims2, _ = analyze(demo_sources([interview]))
    after = next(c for c in claims2 if c["fingerprint"] == gap["fingerprint"])
    assert after["state"] == "uncertain"
    assert after["evidence"][-1]["relation"] == "testimony"


def test_analysis_is_deterministic():
    a, _ = analyze(demo_sources())
    b, _ = analyze(demo_sources())
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_departure_lists_modules_and_questions_for_the_person():
    claims, facts = analyze(demo_sources())
    for c in claims:
        c["review_status"] = "pending"
    d = departure(claims, facts, "Arjun Sharma")
    assert "webhooks/" in d["sole_owner_of"] and "payments/" in d["sole_owner_of"]
    assert d["open_questions"] == len(d["questions"]) > 5
    assert any("asynchronous" in q["question"] for q in d["questions"])


def test_readiness_gives_no_credit_for_conflicts_or_gaps():
    mk = lambda state, review: {"state": state, "review_status": review}
    assert readiness([mk("verified", "approved")])["score"] == 100
    assert readiness([mk("conflicting", "pending"), mk("missing", "pending")])["score"] == 0
    assert readiness([mk("verified", "approved"), mk("conflicting", "pending")])["score"] == 50


def test_polarity_and_passages():
    assert polarity("The migration is half done")["status"] == "open"
    assert polarity("Status: Done.")["status"] == "done"
    assert polarity("Retries run synchronously")["timing"] == "synchronous"
    text = "# Title\n\nFirst sentence is long enough here.\nIt wraps onto a second line.\n\n- A bullet that is long enough to keep.\n"
    assert [s for _, s in doc_passages(text)] == ["First sentence is long enough here.", "It wraps onto a second line.",
                                                    "A bullet that is long enough to keep."]


def test_llm_quote_lock_drops_anything_not_in_the_document():
    doc = "We decided to cache gateway responses for five minutes.\nSomething else entirely."
    kept = llm.quote_lock(["We decided to cache gateway responses for five minutes.",
                           "We decided to cache responses for an hour."], doc)
    assert [k["quote"] for k in kept] == ["We decided to cache gateway responses for five minutes."]
    assert kept[0]["line"] == 1
