"""Optional LLM step. Off unless LLM_API_KEY is set.

The model may only point at sentences that are already in the document. Anything it returns
that is not found word for word in the source is thrown away (the "quote lock"), and what
survives is verified by the same rules as every other claim. The model never sets a state.
"""
import json
import os
import re

import httpx

PROMPT = """You help with project handovers. From the document below, list the sentences that state a decision,
an owner, a risk, a pending task or a dependency between components.
Copy each sentence EXACTLY as written. Do not paraphrase, merge or invent.
Answer with a JSON array of strings and nothing else.

DOCUMENT:
"""


def enabled():
    return bool(os.environ.get("LLM_API_KEY"))


def _norm(s):
    return re.sub(r"\s+", " ", s).strip()


def quote_lock(candidates, document):
    """Keep only candidates that appear verbatim in the document. Returns [{quote, line}]."""
    flat, kept = _norm(document), []
    lines = document.splitlines()
    for c in candidates:
        if not isinstance(c, str):
            continue
        q = _norm(c).strip("-* ")
        if len(q) < 20 or q not in flat:
            continue
        head = q[:30]
        line = next((n for n, text in enumerate(lines, 1) if head in _norm(text)), 0)
        kept.append({"quote": q, "line": line})
    return kept


def extract_claims(document):
    if not enabled() or not document.strip():
        return []
    base = os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
    try:
        r = httpx.post(
            base + "/chat/completions", timeout=40,
            headers={"Authorization": "Bearer " + os.environ["LLM_API_KEY"]},
            json={"model": os.environ.get("LLM_MODEL", ""), "temperature": 0,
                  "messages": [{"role": "user", "content": PROMPT + document[:12000]}]},
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
        text = re.sub(r"```(?:json)?|```", "", text).strip()
        return quote_lock(json.loads(text[text.index("["): text.rindex("]") + 1]), document)
    except Exception:
        return []  # the rule-based extractor still runs, so a failed call loses nothing essential
