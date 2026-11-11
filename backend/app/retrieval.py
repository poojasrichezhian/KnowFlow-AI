"""Small TF-IDF index used to find evidence for a claim. Pure Python, no model download."""
import math
import re
from collections import Counter

STOP = set("""a an the and or but if then else of to in on at by for with from into over under as is are was were be been
being it its this that these those we you they he she i our your their his her not no do does did done can could will
would should may might must have has had so than too very just also about after before when where which who what why
how all any some each per via now still going forward there here out up down off only
known issue decision module pending status note notes team every""".split())

_word = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]+|\d+")


def stem(w):
    for suf, rep in (("ies", "y"), ("ied", "y"), ("ously", "ous"), ("ing", ""), ("ed", ""), ("ly", ""), ("es", ""), ("s", "")):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: len(w) - len(suf)] + rep
    return w


def tokens(text):
    out = []
    for w in _word.findall(text.lower()):
        for part in w.split("_"):
            if part and part not in STOP and len(part) > 1:
                out.append(stem(part))
    return out


class Index:
    """Cosine similarity over TF-IDF vectors of short text chunks."""

    def __init__(self, chunks):
        self.chunks = chunks
        self.toks = [tokens(c["text"]) for c in chunks]
        df = Counter()
        for t in self.toks:
            df.update(set(t))
        n = max(len(chunks), 1)
        self.idf = {w: math.log((1 + n) / (1 + d)) + 1 for w, d in df.items()}
        self.vecs = [self._vec(t) for t in self.toks]

    def _vec(self, toks):
        tf = Counter(toks)
        v = {w: (1 + math.log(c)) * self.idf.get(w, 1.0) for w, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {w: x / norm for w, x in v.items()}

    def search(self, text, k=8, skip=None):
        q = self._vec(tokens(text))
        qset = set(q)
        hits = []
        for i, v in enumerate(self.vecs):
            if skip and skip(self.chunks[i]):
                continue
            shared = qset & set(v)
            if not shared:
                continue
            sim = sum(q[w] * v[w] for w in shared)
            hits.append((sim, len(shared), self.chunks[i]))
        hits.sort(key=lambda h: -h[0])
        return hits[:k]
