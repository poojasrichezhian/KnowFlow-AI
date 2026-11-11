"""KnowFlow AI verification engine.

analyze(sources) is a pure function: the same sources always give the same claims.
Every claim carries its evidence and one of four states:

  verified     - backed by repository history/code, or by two independent sources that agree
  uncertain    - stated in one place only, or supported by indirect evidence
  conflicting  - two sources disagree (never resolved automatically)
  missing      - something a successor needs, with no source that explains it

No language model decides a state. Where an LLM is configured it may only propose
extra claims from documents; they go through exactly the same checks as everything else.
"""
import csv
import hashlib
import io
import json
import os
import re
from collections import Counter

from .github_ingest import is_code, is_doc, is_test
from .retrieval import Index, stem, tokens

T_TOPIC = 0.13    # below this two passages are not about the same thing
T_SUPPORT = 0.30  # at or above this, with 3+ shared terms, an independent passage counts as corroboration

CATEGORIES = ["ownership", "architecture", "decision", "task", "risk", "config", "doc"]


def fp(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


def norm(text):
    return re.sub(r"\s+", " ", text).strip()


# --------------------------------------------------------------------------- text helpers

_NAME = r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)"
OWN_ACTIVE = re.compile(_NAME + r"\s+(?:now\s+)?(?:owns|maintains|is responsible for|is the owner of|will own|leads|looks after)\s+(?:the\s+)?(.+)")
OWN_PASSIVE = re.compile(r"(?:[Tt]he\s+)?(.+?)\s+(?:is|are)\s+(?:owned|maintained)\s+by\s+" + _NAME)
KW = {
    "task": re.compile(r"\b(pending|todo|to do|in progress|not started|half[- ]done|remaining|completed|is complete|finished|unfinished)\b", re.I),
    "risk": re.compile(r"\b(risk|known issue|workaround|fragile|breaks?|lost|careful|must not|bug|hack|vulnerab\w+|outage|fails?)\b", re.I),
    "decision": re.compile(r"\b(decision|decided|agreed|we will|we chose|chose to|moved to|switched to|set to|we use|adopted)\b", re.I),
    "architecture": re.compile(r"\b(depends on|calls|feeds|consumes|talks to|stored in|pushed to|publishes to|reads from|writes to)\b", re.I),
}
EXPLICIT = re.compile(r"^\s*decision\b|\b(we decided|decided to|we agreed|agreed to|we chose|known issue|workaround)\b", re.I)
RATIONALE = re.compile(r"\b(because|so that|since|due to|in order to|to avoid|to prevent|to stop|as a workaround)\b", re.I)

OPEN = re.compile(r"\b(to do|todo|in progress|pending|not started|half[- ]done|not (?:yet )?(?:written|done|implemented|finished|complete)|unfinished)\b", re.I)
DONE = re.compile(r"\b(completed?|done|finished|closed|resolved|merged|shipped|(?:was|were|been) (?:moved|migrated|switched))\b", re.I)
ASYNC = re.compile(r"\b(asynchronous(?:ly)?|async|background|non-?blocking)\b", re.I)
SYNC = re.compile(r"\b(synchronous(?:ly)?|sync|blocking|blocks? the)\b", re.I)
ON = re.compile(r"\b(enabled|turned on)\b", re.I)
OFF = re.compile(r"\b(disabled|turned off)\b", re.I)


def polarity(text):
    """Which side of each either/or a passage is on. Used only to detect contradictions."""
    p = {}
    if OPEN.search(text):
        p["status"] = "open"
    elif DONE.search(text):
        p["status"] = "done"
    a, s = bool(ASYNC.search(text)), bool(SYNC.search(text))
    if a != s:
        p["timing"] = "asynchronous" if a else "synchronous"
    on, off = bool(ON.search(text)), bool(OFF.search(text))
    if on != off:
        p["switch"] = "enabled" if on else "disabled"
    return p


def disagreement(a, b):
    pa, pb = polarity(a), polarity(b)
    for key in pa:
        if key in pb and pa[key] != pb[key]:
            return f"one says {pa[key]}, the other says {pb[key]}"
    return None


def doc_passages(text):
    """Yield (line_number, sentence) for prose in a markdown/plain document. Wrapped lines are joined."""
    out, buf, start, fenced = [], [], 0, False

    def flush():
        if buf:
            para = norm(" ".join(buf))
            for s in re.split(r"(?<=[.!?])\s+(?=[A-Z`])", para):
                s = s.strip()
                if 20 <= len(s) <= 320:
                    out.append((start, s))
            buf.clear()

    for n, line in enumerate(text.splitlines(), 1):
        raw = line.rstrip()
        if raw.strip().startswith("```"):
            fenced = not fenced
            flush()
            continue
        if fenced or not raw.strip() or raw.startswith("    ") or raw.lstrip().startswith(("#", "|", ">", "---", "===", "<!--", ".. ")):
            flush()
            continue
        bullet = re.match(r"\s*(?:[-*+]|\d+[.)])\s+(.*)", raw)
        if bullet:
            flush()
            buf.append(bullet.group(1))
            start = n
        else:
            if not buf:
                start = n
            buf.append(raw.strip())
    flush()
    return out


def code_comments(text):
    """Yield (line_number, comment_text) for docstrings and comment blocks."""
    out, lines = [], text.splitlines()
    for m in re.finditer(r'("""|\'\'\')(.+?)\1', text, re.S):
        body = norm(m.group(2))
        if len(body) >= 15:
            out.append((text.count("\n", 0, m.start()) + 1, body[:400]))
    block, start = [], 0
    for n, line in enumerate(lines + [""], 1):
        m = re.match(r"\s*(?:#(?!!)|//|--|\*(?!/))\s?(.*)", line)
        inline = re.search(r"\s(?:#|//)\s*((?:TODO|FIXME|HACK|XXX)\b.*)", line) if not m else None
        if m and m.group(1).strip():
            if not block:
                start = n
            block.append(m.group(1).strip())
            continue
        if block:
            body = norm(" ".join(block))
            if len(body) >= 15:
                out.append((start, body[:400]))
            block = []
        if inline:
            out.append((n, norm(inline.group(1))[:400]))
    return out


def classify(sentence):
    if OWN_ACTIVE.search(sentence) or OWN_PASSIVE.search(sentence):
        return "ownership"
    if re.match(r"\s*decision\b", sentence, re.I):
        return "decision"
    for cat in ("risk", "task", "decision", "architecture"):
        if KW[cat].search(sentence):
            return cat
    return None


def same_person(a, b):
    a, b = a.lower().strip(), b.lower().strip()
    if not a or not b:
        return False
    return a == b or a.split()[0] == b.split()[0] or a in b or b in a


def short(text, n=90):
    text = norm(text)
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


# --------------------------------------------------------------------------- analysis

class Analysis:
    def __init__(self, sources):
        self.sources = sources
        self.claims = []
        self.chunks = []
        self.owners = {}        # module -> Counter(author)
        self.module_src = {}    # module -> github source
        self.people = set()
        self.doc_text = ""      # every document, for "is X documented anywhere?"
        self.text_claims = []   # (source, sub, line, sentence, origin)
        self.seen = set()

    # -- small builders
    def ev(self, src, relation, excerpt, locator="", url=None, kind="quote"):
        return {"source_id": src["id"], "source": src["name"], "source_kind": src["kind"], "relation": relation,
                "excerpt": norm(excerpt)[:400], "locator": locator, "url": url, "kind": kind}

    def chunk_ev(self, ch, relation):
        return self.ev(ch["src"], relation, ch["text"], ch["locator"], ch["url"])

    def add(self, key, category, title, text, state, why, evidence, module="", people=(), origin="rule", origin_source=None):
        f = fp(*key)
        if f in self.seen:
            return
        self.seen.add(f)
        self.claims.append({
            "fingerprint": f, "category": category, "title": short(title, 140), "text": norm(text), "state": state,
            "why": why, "evidence": evidence, "module": module, "people": sorted(set(p for p in people if p)),
            "origin": origin, "origin_source": origin_source,
        })

    def chunk(self, src, sub, text, locator, url, kind):
        self.chunks.append({"src": src, "sid": src["id"], "sub": sub, "text": text, "locator": locator, "url": url, "kind": kind})

    def canon(self, name):
        for p in sorted(self.people):
            if same_person(name, p):
                return p
        return name

    def module_for(self, text):
        stems = set(tokens(text))
        for m in self.owners:
            base = stem(os.path.splitext(os.path.basename(m.rstrip("/")))[0].lower())
            if base in stems:
                return m
        return ""

    # -- pass 1: read every source into chunks
    def load(self):
        for src in self.sources:
            kind = src["kind"]
            if kind == "github":
                self.load_repo(src, json.loads(src["content"]))
            elif kind == "tasks":
                self.load_tasks(src)
            elif kind == "interview":
                for i, item in enumerate(json.loads(src["content"] or "[]")):
                    self.chunk(src, f"a{i}", item["answer"], f"answer from {item.get('person') or 'team member'}", None, "testimony")
                    self.doc_text += "\n" + item["answer"]
            else:
                self.doc_text += "\n" + src["content"]
                for line, s in doc_passages(src["content"]):
                    self.chunk(src, "", s, f"line {line}", None, "doc")
                    self.text_claims.append((src, "", line, s, "rule"))
                for item in (src.get("meta") or {}).get("llm_claims", []):
                    self.text_claims.append((src, "", item.get("line", 0), item["quote"], "llm"))

    def load_repo(self, src, snap):
        repo, branch = snap["repo"], snap["branch"]
        link = not snap.get("no_links")
        src["_snap"] = snap

        def blob(path, line=None):
            return f"https://github.com/{repo}/blob/{branch}/{path}" + (f"#L{line}" if line else "") if link else None

        src["_blob"] = blob
        seen_commits = set()
        for m, commits in snap["module_commits"].items():
            self.owners[m] = Counter(c["author"] for c in commits)
            self.module_src[m] = src
            self.people.update(c["author"] for c in commits)
            for c in commits:
                if c["sha"] not in seen_commits:
                    seen_commits.add(c["sha"])
                    self.chunk(src, "commit:" + c["sha"], c["message"], f"commit {c['sha'][:7]} by {c['author']}, {c['date']}",
                               c["url"] if link else None, "commit")
        for path, text in snap["files"].items():
            if is_doc(path):
                self.doc_text += "\n" + text
                for line, s in doc_passages(text):
                    self.chunk(src, path, s, f"{path}:L{line}", blob(path, line), "doc")
                    # Repository docs are mostly product documentation, so only explicit ownership and
                    # decision statements are treated as handover claims. Everything else is evidence.
                    if OWN_ACTIVE.search(s) or OWN_PASSIVE.search(s) or EXPLICIT.search(s):
                        self.text_claims.append((src, path, line, s, "rule"))
            else:
                for line, c in code_comments(text):
                    self.chunk(src, path, c, f"{path}:L{line}", blob(path, line), "code")
        for i in snap.get("issues", []):
            self.chunk(src, f"issue:{i['number']}", f"{i['title']}. Status: open.", f"issue #{i['number']}", i["url"], "issue")

    def load_tasks(self, src):
        rows = list(csv.DictReader(io.StringIO(src["content"])))
        src["_tasks"] = []
        for n, row in enumerate(rows, 2):
            low = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}

            def col(*names):
                return next((low[x] for x in names if low.get(x)), "")

            task = {"key": col("key", "id", "issue key", "ticket") or f"row {n}", "title": col("summary", "title", "task", "name"),
                    "status": col("status", "state"), "assignee": col("assignee", "owner", "assigned to"), "row": n}
            if task["assignee"].lower() in ("unassigned", "none", "-"):
                task["assignee"] = ""
            if not task["title"]:
                continue
            task["text"] = f"{task['key']}: {task['title']}. Status: {task['status'] or 'unknown'}."
            if task["assignee"]:
                self.people.add(task["assignee"])
            src["_tasks"].append(task)
            self.chunk(src, "", task["text"], f"row {n}", None, "task")

    # -- pass 2: facts that come straight from the repository
    def repo_facts(self, src):
        snap, blob = src["_snap"], src["_blob"]
        link = not snap.get("no_links")
        tree = set(snap["tree"])
        dirs = {p.rsplit("/", 1)[0] + "/" for p in tree if "/" in p}
        modules = snap["modules"]

        def commit_ev(c, relation="supports"):
            return self.ev(src, relation, c["message"], f"commit {c['sha'][:7]} by {c['author']}, {c['date']}", c["url"] if link else None)

        # ownership and single-owner risk
        for m in modules:
            commits = snap["module_commits"].get(m, [])
            if not commits:
                continue
            counts = self.owners[m]
            top, n = counts.most_common(1)[0]
            share = round(100 * n / len(commits))
            mine = [c for c in commits if c["author"] == top]
            state, why = ("verified", f"Counted from {len(commits)} commits in the repository history.") if len(commits) >= 2 else \
                ("uncertain", "Only one commit touches this module, which is thin evidence of ownership.")
            others = ", ".join(f"{a} {c}" for a, c in counts.most_common()[1:4])
            self.add(("own", snap["repo"], m), "ownership", f"{top} is the main contributor to {m}",
                     f"{top} made {n} of the last {len(commits)} commits to `{m}` ({share}%)." + (f" Others: {others}." if others else ""),
                     state, why, [commit_ev(c) for c in mine[:3]], m, [top])
            if share >= 75 and len(commits) >= 3:
                self.add(("bus", snap["repo"], m), "risk", f"Only {top} knows {m}",
                         f"{share}% of commits to `{m}` are by {top}. If {top.split()[0]} leaves, nobody else has hands-on history with this module.",
                         "verified", f"Counted from {len(commits)} commits in the repository history.",
                         [commit_ev(c) for c in mine[:2]], m, [top])

        # dependencies between modules, read from import statements
        names = {os.path.splitext(os.path.basename(m.rstrip("/")))[0]: m for m in modules}
        for path, text in snap["files"].items():
            a = next((m for m in modules if path == m or path.startswith(m)), None)
            if not a or not is_code(path) or is_test(path):
                continue
            for n, line in enumerate(text.splitlines(), 1):
                target = None
                m = re.match(r"\s*(?:from|import)\s+\.*([A-Za-z_][\w.]*)", line)
                if m:
                    target = next((names[seg] for seg in m.group(1).split(".") if seg in names), None)
                else:
                    m = re.search(r"""(?:from|require\()\s*['"](\.{1,2}/[^'"]+)['"]""", line)
                    if m:
                        resolved = os.path.normpath(os.path.join(os.path.dirname(path), m.group(1))).replace("\\", "/")
                        target = next((mod for mod in modules if resolved.startswith(mod.rstrip("/"))), None)
                if target and target != a:
                    self.add(("dep", snap["repo"], a, target), "architecture", f"{a} depends on {target}",
                             f"`{a}` imports from `{target}`, so a change to `{target}` can break `{a}`.",
                             "verified", "Read from an import statement in the code.",
                             [self.ev(src, "supports", line.strip(), f"{path}:L{n}", blob(path, n))], a)

        # notes left in code: TODO / FIXME / HACK
        count = 0
        for path, text in snap["files"].items():
            if not is_code(path) or is_test(path):
                continue
            for n, c in code_comments(text):
                m = re.search(r"\b(TODO|FIXME|HACK|XXX)\b[:\s-]*(.+)", c)
                if m and count < 15:
                    count += 1
                    mod = next((x for x in modules if path == x or path.startswith(x)), "")
                    owner = self.owners.get(mod, Counter()).most_common(1)
                    self.add(("todo", snap["repo"], path, norm(m.group(2))), "risk",
                             f"{m.group(1)} in {path}: {m.group(2)}",
                             f"{m.group(1)} in `{path}`: {m.group(2)}",
                             "verified", "The note is in the code itself.",
                             [self.ev(src, "supports", c, f"{path}:L{n}", blob(path, n))], mod, [owner[0][0]] if owner else [])

        # configuration the code reads
        env = {}
        for path, text in snap["files"].items():
            if not is_code(path) or is_test(path):
                continue
            for n, line in enumerate(text.splitlines(), 1):
                for m in re.finditer(r"""(?:os\.environ(?:\.get)?\s*[\[(]\s*|os\.getenv\(\s*|process\.env\.|System\.getenv\(\s*)['"]?([A-Z][A-Z0-9_]{2,})""", line):
                    env.setdefault(m.group(1), (path, n, line.strip()))
        for name, (path, n, line) in sorted(env.items()):
            mod = next((x for x in modules if path == x or path.startswith(x)), "")
            owner = self.owners.get(mod, Counter()).most_common(1)
            code_ev = self.ev(src, "context", line, f"{path}:L{n}", blob(path, n))
            if re.search(r"\b" + re.escape(name) + r"\b", self.doc_text):
                self.add(("env", snap["repo"], name), "config", f"{name} is needed to run {mod or 'the project'}",
                         f"`{name}` is read in `{path}` and is described in the project documents.",
                         "verified", "Used in code and mentioned in a document.", [dict(code_ev, relation="supports")], mod)
            else:
                self.add(("env", snap["repo"], name), "config", f"{name} is not documented",
                         f"`{name}` is read in `{path}`, but no document says what it is for or where its value comes from.",
                         "missing", "Searched every connected document for this name and found nothing.",
                         [code_ev], mod, [owner[0][0]] if owner else [])

        # documents that point at files which are not there
        for path, text in snap["files"].items():
            if not is_doc(path):
                continue
            for n, line in enumerate(text.splitlines(), 1):
                for ref in re.findall(r"`([\w./-]+/[\w.-]*)`", line):
                    ref = ref.lstrip("./")
                    looks_like_path = ref.endswith("/") or re.search(r"\.\w{1,5}$", ref)
                    exists = ref in tree or ref in dirs or (ref + "/") in dirs
                    if looks_like_path and not exists:
                        self.add(("path", snap["repo"], path, ref), "doc", f"{path} points to {ref}, which does not exist",
                                 f"`{path}` refers to `{ref}`, but there is no such path in the repository.",
                                 "conflicting", "The document and the repository file list disagree.",
                                 [self.ev(src, "states", line, f"{path}:L{n}", blob(path, n)),
                                  self.ev(src, "contradicts", f"No path named {ref} among the {len(tree)} files in {snap['repo']}.",
                                          "repository file list", None, "computed")], self.module_for(ref))

        # README older than the code it describes
        if snap.get("readme_commits"):
            last = snap["readme_commits"][0]
            newer = {c["sha"]: c for cs in snap["module_commits"].values() for c in cs if c["date"] > last["date"]}
            if len(newer) >= 5:
                latest = max(newer.values(), key=lambda c: c["date"])
                self.add(("stale", snap["repo"], snap["readme"]), "doc", f"{snap['readme']} may be out of date",
                         f"`{snap['readme']}` was last changed on {last['date']}. The code has had {len(newer)} commits since then.",
                         "uncertain", "Age is indirect evidence: the README might still be right, but nobody has checked.",
                         [commit_ev(last, "context"), commit_ev(latest, "context")])

        # modules with no tests
        tests = {p: t for p, t in snap["files"].items() if is_test(p)}
        any_tests = any(is_test(p) for p in tree)
        for m in modules:
            base = os.path.splitext(os.path.basename(m.rstrip("/")))[0]
            covered = any(base in p or re.search(r"\b" + re.escape(base) + r"\b", t) for p, t in tests.items())
            if not covered:
                owner = self.owners.get(m, Counter()).most_common(1)
                self.add(("tests", snap["repo"], m), "risk", f"No tests found for {m}",
                         f"No test file imports or names `{m}`." + ("" if any_tests else " The repository has no test files at all."),
                         "missing", "Looked through the test files in the repository.",
                         [self.ev(src, "context", f"{len(tests)} test files read; none reference {base}.", "repository test files", None, "computed")],
                         m, [owner[0][0]] if owner else [])

        # open issues and pull requests
        unowned = []
        for i in snap.get("issues", [])[:12]:
            kind = "pull request" if i["is_pr"] else "issue"
            who = i["assignee"] or (i["author"] if i["is_pr"] else "")
            self.add(("issue", snap["repo"], i["number"]), "task", f"Open {kind} #{i['number']}: {i['title']}",
                     f"Open {kind} #{i['number']}: {i['title']}." + (f" Assigned to {i['assignee']}." if i["assignee"] else ""),
                     "verified", "Listed as open on GitHub when the repository was read.",
                     [self.ev(src, "supports", i["title"], f"{kind} #{i['number']}, updated {i['updated']}", i["url"])], "", [who])
            if not i["is_pr"] and not i["assignee"]:
                unowned.append(i)
        if unowned:
            self.add(("unowned", snap["repo"]), "task", f"{len(unowned)} open issue{'s have' if len(unowned) > 1 else ' has'} nobody assigned",
                     "Nobody is assigned to: " + ", ".join(f"#{i['number']}" for i in unowned) + ".",
                     "missing", "GitHub shows no assignee for these issues.",
                     [self.ev(src, "context", i["title"], f"issue #{i['number']}", i["url"]) for i in unowned[:3]])

    # -- pass 3: statements people wrote, checked against everything else
    def check_statement(self, text, src, sub):
        """Look for independent passages that back up or contradict a statement."""
        index_hits = self.index.search(text, k=12, skip=lambda c: c["sid"] == src["id"] and c["sub"] == sub)
        supports, contradicts = [], []
        for sim, shared, ch in index_hits:
            if sim < T_TOPIC or shared < 2:
                continue
            clash = disagreement(text, ch["text"])
            if clash:
                contradicts.append((ch, clash))
            elif sim >= T_SUPPORT and shared >= 3:
                supports.append(ch)
        return supports, contradicts

    def statements(self):
        rationale_gaps = 0
        for src, sub, line, sentence, origin in self.text_claims:
            category = classify(sentence)
            if origin == "llm":
                category = category or "decision"
            if not category:
                continue
            locator = f"{sub}:L{line}" if sub else f"line {line}"
            url = src["_blob"](sub, line) if sub and "_blob" in src else None
            stated = self.ev(src, "states", sentence, locator, url)
            module = self.module_for(sentence)
            people = [p for p in self.people if re.search(r"\b" + re.escape(p.split()[0]) + r"\b", sentence)]
            key = ("text", norm(sentence).lower())

            # "X owns Y" is checked against who actually commits to Y
            m, person, thing = OWN_ACTIVE.search(sentence), None, None
            if m:
                person, thing = m.group(1), m.group(2)
            else:
                m = OWN_PASSIVE.search(sentence)
                if m:
                    thing, person = m.group(1), m.group(2)
            if person and self.module_for(thing):
                mod = self.module_for(thing)
                counts, gsrc = self.owners[mod], self.module_src[mod]
                total = sum(counts.values())
                top, n = counts.most_common(1)[0]
                named = next((a for a in counts if same_person(person, a)), None)
                commits = gsrc["_snap"]["module_commits"][mod]
                link = not gsrc["_snap"].get("no_links")

                def cev(c, rel):
                    return self.ev(gsrc, rel, c["message"], f"commit {c['sha'][:7]} by {c['author']}, {c['date']}", c["url"] if link else None)

                if named and counts[named] / total >= 0.4:
                    self.add(key, "ownership", sentence, sentence, "verified",
                             f"The repository agrees: {named} made {counts[named]} of {total} commits to {mod}.",
                             [stated] + [cev(c, "supports") for c in commits if c["author"] == named][:2],
                             mod, [named], origin, src["id"])
                else:
                    self.add(key, "ownership", sentence, sentence, "conflicting",
                             f"The document names {person}, but {top} made {n} of {total} commits to {mod}"
                             + (f" and {named} made {counts[named]}." if named else f" and {person} made none."),
                             [stated] + [cev(c, "contradicts") for c in commits if c["author"] == top][:2],
                             mod, [self.canon(person), top], origin, src["id"])
                continue

            supports, contradicts = self.check_statement(sentence, src, sub)
            if not module:  # a statement about code belongs to the module that code lives in
                paths = [c["sub"] for c, _ in contradicts] + [c["sub"] for c in supports]
                module = next((m for p in paths for m in self.owners if p.startswith(m)), "")
            evidence = [stated] + [self.chunk_ev(c, "contradicts") for c, _ in contradicts[:2]] + [self.chunk_ev(c, "supports") for c in supports[:2]]
            if contradicts:
                ch, clash = contradicts[0]
                state, why = "conflicting", f"{ch['src']['name']} ({ch['locator']}) disagrees: {clash}."
            elif supports:
                state, why = "verified", f"Backed by an independent source: {supports[0]['src']['name']} ({supports[0]['locator']})."
            else:
                state, why = "uncertain", "Stated in one place only. No other source confirms or contradicts it."
            self.add(key, category, sentence, sentence, state, why, evidence, module, people, origin, src["id"])

            if category == "decision" and state != "conflicting" and not RATIONALE.search(sentence) and rationale_gaps < 8:
                rationale_gaps += 1
                self.add(("why", norm(sentence).lower()), "decision", f"No reason recorded for: {short(sentence, 100)}",
                         f"The decision is written down, but not why it was made: “{short(sentence, 200)}”",
                         "missing", "The statement gives no reason, and no other source explains it.",
                         [dict(stated, relation="context")], module, people, "rule", src["id"])

    def tasks(self):
        for src in self.sources:
            for t in src.get("_tasks", []):
                if polarity(t["text"]).get("status") == "done":
                    continue
                stated = self.ev(src, "states", t["text"], f"row {t['row']}")
                supports, contradicts = self.check_statement(t["text"], src, "")
                evidence = [stated] + [self.chunk_ev(c, "contradicts") for c, _ in contradicts[:2]] + [self.chunk_ev(c, "supports") for c in supports[:2]]
                if contradicts:
                    ch, clash = contradicts[0]
                    state, why = "conflicting", f"{ch['src']['name']} ({ch['locator']}) disagrees: {clash}."
                elif supports:
                    state, why = "verified", f"Backed by an independent source: {supports[0]['src']['name']} ({supports[0]['locator']})."
                else:
                    state, why = "uncertain", "Only the task list mentions this. Task status is often stale."
                who = self.canon(t["assignee"]) if t["assignee"] else ""
                self.add(("task", src["id"], t["key"]), "task", f"{t['key']}: {t['title']}",
                         f"{t['title']}. Status: {t['status'] or 'unknown'}." + (f" Assigned to {who}." if who else ""),
                         state, why, evidence, self.module_for(t["title"]), [who], "rule", src["id"])
                if not who:
                    self.add(("taskowner", src["id"], t["key"]), "task", f"Nobody owns {t['key']}: {t['title']}",
                             f"{t['key']} is open and has no assignee.", "missing", "The task list has no assignee for this task.",
                             [dict(stated, relation="context")], self.module_for(t["title"]), [], "rule", src["id"])

    # -- pass 4: answers given in exit interviews
    def testimony(self):
        by_fp = {c["fingerprint"]: c for c in self.claims}
        for src in self.sources:
            if src["kind"] != "interview":
                continue
            for item in json.loads(src["content"] or "[]"):
                claim = by_fp.get(item.get("fingerprint"))
                if not claim:
                    continue
                who = item.get("person") or "a team member"
                claim["evidence"].append(self.ev(src, "testimony", item["answer"], f"exit interview answer from {who}, {item.get('at', '')}"))
                claim["answered"] = True
                if claim["state"] == "missing":
                    claim["state"] = "uncertain"
                    claim["why"] = f"Explained by {who} in an exit interview. One person's account, not yet confirmed by another source."
                elif claim["state"] == "uncertain":
                    claim["state"] = "verified"
                    claim["why"] = f"Stated in a source and confirmed by {who} in an exit interview."
                elif claim["state"] == "conflicting":
                    claim["why"] += f" {who} has given an account; a reviewer still has to decide which source is right."

    def run(self):
        self.load()
        self.index = Index(self.chunks)
        for src in self.sources:
            if src["kind"] == "github":
                self.repo_facts(src)
        self.statements()
        self.tasks()
        self.testimony()
        order = {"conflicting": 0, "missing": 1, "uncertain": 2, "verified": 3}
        self.claims.sort(key=lambda c: (order[c["state"]], CATEGORIES.index(c["category"]), c["title"]))
        return self.claims


def analyze(sources):
    """sources: list of dicts with id, kind, name, visibility, content, meta."""
    a = Analysis([dict(s) for s in sources])
    claims = a.run()
    return claims, {"people": sorted(a.people), "owners": {m: dict(c) for m, c in a.owners.items()}}


# --------------------------------------------------------------------------- readiness

WEIGHT = {("verified", "approved"): 1.0, ("verified", "pending"): 0.6, ("uncertain", "approved"): 0.5, ("uncertain", "pending"): 0.3}


def readiness(claims):
    """0-100. Only reviewed, verified knowledge counts in full; open conflicts and gaps count for nothing."""
    live = [c for c in claims if c["review_status"] != "rejected"]
    counts = Counter(c["state"] for c in live)
    if not live:
        return {"score": 0, "counts": {}, "total": 0, "approved": 0, "pending": 0}
    score = sum(WEIGHT.get((c["state"], c["review_status"]), 0.0) for c in live) / len(live)
    return {"score": round(100 * score), "counts": dict(counts), "total": len(live),
            "approved": sum(c["review_status"] == "approved" for c in live),
            "pending": sum(c["review_status"] == "pending" for c in live)}


# --------------------------------------------------------------------------- departure simulator

def question_for(c):
    text = short(c["text"], 220)
    if c["state"] == "conflicting":
        return f"Our sources disagree here: “{text}” Which version is true today, and which source needs correcting?"
    if c["state"] == "missing" and c["category"] == "config":
        name = c["title"].split()[0]
        return f"What is {name} for, where does its value come from, and what breaks if it is not set?"
    if c["state"] == "missing" and c["category"] == "decision":
        return f"Why was this decided, and what alternatives were rejected? {text}"
    if c["state"] == "missing" and c["title"].startswith("No tests"):
        return f"There are no tests for {c['module']}. How do you check it still works after a change?"
    if c["state"] == "missing":
        return f"Nobody has written this down: {text} What should your successor know?"
    if c["state"] == "uncertain":
        return f"Only one source mentions this: “{text}” Is it still accurate, and what is the current status?"
    if c["title"].startswith("Only "):
        return f"You wrote most of {c['module']}. What would a new owner get wrong in their first month? Name the non-obvious behaviour and who else to ask."
    return f"This note is in the code: “{text}” How serious is it, and what is the workaround or planned fix?"


def departure(claims, facts, person):
    """What the project loses if this person leaves, and the questions to ask them before they go."""
    modules = []
    for m, counts in facts["owners"].items():
        total = sum(counts.values())
        mine = sum(n for a, n in counts.items() if same_person(a, person))
        if mine:
            modules.append({"module": m, "commits": mine, "total": total, "share": round(100 * mine / total),
                            "others": sorted(a for a in counts if not same_person(a, person))})
    modules.sort(key=lambda x: -x["share"])
    primary = {m["module"] for m in modules if m["share"] >= 50}
    questions, tasks = [], []
    for c in claims:
        if c["review_status"] == "rejected":
            continue
        named = any(same_person(p, person) for p in c.get("people", []))
        if c["category"] == "task" and named and c["state"] != "missing":
            tasks.append(c)
        involved = named or (c.get("module") in primary)
        needs_answer = c["state"] != "verified" or (c["category"] == "risk" and c["origin"] == "rule" and c["origin_source"] is None)
        if involved and (needs_answer or c.get("answered")):
            questions.append({"fingerprint": c["fingerprint"], "claim_id": c.get("id"), "state": c["state"], "title": c["title"],
                              "question": question_for(c), "answered": bool(c.get("answered")),
                              "answer": next((e["excerpt"] for e in reversed(c["evidence"]) if e["relation"] == "testimony"), None)})
    return {"person": person, "modules": modules, "sole_owner_of": [m["module"] for m in modules if m["share"] >= 75],
            "tasks": [{"title": t["title"], "state": t["state"]} for t in tasks], "questions": questions,
            "open_questions": sum(not q["answered"] for q in questions)}
