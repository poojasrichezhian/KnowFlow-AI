# Round 2 form: draft answers

Fill the bracketed parts, and delete any line that is not true of YOUR deployed link when you submit.

## Your team

- Hackathon name: [the form lists CodeTitan India 2026, CodersInPune, CodePuneThinkers, CodeFrontier. Your Round 1 deck says "HackWithPune 2026". Confirm with the organisers which option is yours before submitting.]
- Team name: [exactly as in Round 1]
- Team leader, email: [same email as Round 1]
- Members: Poojasri I S / Aadarshini S S / Surya Prakash M

## Links

- Functioning project: [deployed URL]
- Source code: [public GitHub URL]
- Updated PDF: [Drive link, Anyone with the link, Viewer]

## The list of features you completed

```
One-click demo sign-in for three roles (project manager, developer, new team member), no account needed
Account sign-up and sign-in with JWT sessions and hashed passwords
Create a project from any public GitHub repository URL
GitHub reader: commit history per module, code comments, imports, documents, open issues and pull requests
Upload PDF, DOCX, Markdown and text documents; paste meeting notes; import a task list from CSV
Claim extraction for ownership, decisions, risks, tasks, architecture, configuration and documentation
Every claim labelled Verified, Uncertain, Conflicting or Missing, with the reason for the label shown
Evidence viewer: each claim lists the exact quoted passage, file and line or commit, with a link to GitHub
Conflict detection: named owner vs commit history
Conflict detection: marked done in notes vs still open in the task list or code
Conflict detection: opposite statements about the same thing (asynchronous vs synchronous, enabled vs disabled)
Conflict detection: documents that refer to files which do not exist in the repository
Missing-knowledge detection: undocumented environment variables, modules without tests, tasks without an owner, decisions with no recorded reason
Module ownership and single-owner risk calculated from commits
Module dependencies read from import statements (Python, JavaScript, TypeScript)
Departure simulator: pick a person and see the modules and open work only they know
Exit interview: one generated question per gap, conflict or risk tied to that person; answers are stored as evidence and re-verified
Handover readiness score with a breakdown by state
Human review: approve, reject, edit wording, reopen; bulk-approve verified claims
Conflicts cannot be approved until a reviewer resolves them with a written reason
Publish handover versions with version history
Role-based handover reports for project manager, developer and new team member
Download any handover as Markdown
Role-based access control with project membership checks on every request
Managers-only sources: claims that rely on them are hidden from other roles
Team management: add or remove members and set roles
Bundled demo project with a reset button
```

Only if you set LLM_API_KEY on the server and tested it yourself, add:
`Optional LLM extraction from documents with a quote lock (output not found word for word in the source is discarded)`

## Technology and implementation details

Frontend: React 18 built with Vite, plain CSS, no UI library. Backend: Python, FastAPI, Pydantic, SQLAlchemy.
Database: SQLite by default, PostgreSQL through DATABASE_URL [say which one your deployment uses]. Auth: JWT (PyJWT),
PBKDF2 password hashing, role checks on every project route. Documents: PyMuPDF for PDF, python-docx for DOCX.
Integration: GitHub REST API (repository, tree, commits per path, issues) plus raw file contents.
Deployment: one Docker image; FastAPI serves the built React app, so there is a single URL. [hosting provider]

How it fits together: sources are stored as text or as a repository snapshot. The verifier (backend/app/engine.py) is a
pure function that turns all sources of a project into claims. It runs in four passes: (1) split every source into
passages with a file-and-line or commit locator; (2) derive facts straight from the repository; (3) take each statement
people wrote and search all other sources for passages about the same thing, using a TF-IDF index we wrote; (4) apply
exit-interview answers. A statement becomes Verified only when an independent source backs it, Conflicting when one
disagrees, Uncertain when nothing else mentions it. Review decisions are stored per claim fingerprint so they survive
re-analysis, and are dropped automatically if the underlying evidence changes the claim's state.

What was technically hard:
- Making the state of a claim reproducible. No language model decides a state; identical sources always give identical
  output (covered by a test).
- Evidence that cannot be invented. Every quoted excerpt is taken from the stored source, and a test asserts that each
  one is found verbatim in its source.
- Keeping human review stable across re-analysis without letting a stale approval hide a new conflict.
- Source-level permissions that also apply to derived claims and to already published versions.
- Running on a 512 MB free host: no model download, analysis of the demo project takes well under a second.
- 17 automated tests cover the verifier, the four conflict checks, the exit-interview rule and the GitHub reader.

## What changed from your original proposal, and why?

Added
- Departure simulator and exit interview. Round 1 only reconstructed knowledge after someone left. We realised the
  cheapest moment to capture it is before they go, so the product now turns every gap into a question for that person.
- Handover readiness score, so a manager can see whether a handover is safe to publish.
- Facts derived directly from the repository (ownership from commits, imports, TODO notes, undocumented configuration,
  broken file references). These need no AI and are the strongest evidence we have.

Replaced
- LLM-first extraction became a rule-based verifier with an optional LLM step. Our core promise is "no claim without
  proof"; letting a model assign Verified would break it. The LLM may only propose sentences, and a quote lock discards
  anything not present word for word in the document.
- ChromaDB and Sentence Transformers became an in-process TF-IDF index. The embedding model did not fit the memory of
  free hosting, and a judge must be able to open the link. Semantic retrieval is our first Round 3 improvement.
- LangChain was dropped: one HTTP call did not justify the dependency.
- PostgreSQL is supported but SQLite is the default, to keep the deployment to one service.

Not built
- Direct Jira and Google Drive connections (never in the MVP). Task lists come in as CSV exports and documents as uploads.
- The visual dependency graph. Dependencies are detected and listed as claims, not drawn.

## What does NOT work yet?

- Evidence matching is word-based. If two sources say the same thing in different words, the claim stays Uncertain
  instead of Verified, and a paraphrased contradiction is not caught.
- Word matching can also over-match: a statement that shares several terms with another source can be marked
  Verified even though one detail differs. This is one reason nothing is published without human approval.
- Only the four conflict types listed above are detected. Numbers that disagree (for example two different limits) are not.
- Statement extraction is pattern-based and English only. Vague sentences are skipped; a sentence with two facts becomes one claim.
- Private repositories are not supported. For large repositories we read up to 8 modules, 45 code files, the last 100
  commits per module and 30 open issues.
- Import analysis covers Python and JavaScript/TypeScript. Other languages get ownership and TODO claims but no dependencies.
- Scanned PDFs (images without text) cannot be read.
- No email invitations: a person must sign up before a manager can add them to a project.
- The demo project is shared by everyone who opens it, so another visitor's reviews may be visible. "Reset demo"
  (as project manager) restores it.
- [If on a free host] The first load after idle can take up to a minute.
- [If using SQLite] Accounts and projects other than the demo are lost when the server restarts.
- [If DEMO_REPO is not set] Demo evidence shows file, line and quote but no GitHub link. Projects created from a real repository do link.
- [Unless you enabled and tested it] The LLM step is switched off on the live site.

## Three improvements for Round 3

**1. Semantic verification with a measured accuracy.**
Add an embedding index and an LLM entailment check (supports / contradicts / unrelated) behind the existing quote lock,
so the verifier catches agreement and contradiction that use different words, including notes versus what the code
actually does. We will publish precision and recall on a labelled set of seeded contradictions inside the product.
For the user: fewer claims stuck at Uncertain, and conflicts found that today need a human to notice.

**2. Continuous handover with drift alerts.**
Re-read connected repositories on a schedule and by GitHub webhook. When new commits or documents change the evidence
under an approved claim, mark it Stale, show what changed since the published version, and list it in an alerts feed
for the reviewer. For the user: a handover that stays true after it is published, instead of a snapshot that ages.

**3. Ask the handover.**
A question box over the published handover that answers only from approved claims, cites the evidence for every
sentence, and says "not in the handover" otherwise. Unanswered questions are logged as new Missing items and feed the
next exit interview. For the user: a newcomer gets answers in seconds, and every question nobody could answer becomes
a tracked knowledge gap.
