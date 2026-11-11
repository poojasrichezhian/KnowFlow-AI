"""GitHub ingestion against a fake API that returns the same JSON shapes as api.github.com."""
import httpx
import pytest

from app import github_ingest
from app.engine import analyze
from app.github_ingest import GitHubError, fetch_snapshot, parse_repo, pick_modules
import json

FILES = {
    "README.md": "# Shop\n\nSet `SHOP_DB` before starting. See `billing/missing.py`.\n",
    "billing/invoice.py": "import os\nfrom cart.items import total\n# TODO: handle refunds\nDB = os.environ['SHOP_DB']\nKEY = os.environ['SHOP_KEY']\n",
    "cart/items.py": '"""Cart items and totals."""\n\ndef total():\n    return 0\n',
}


def commit(sha, name, msg):
    return {"sha": sha * 40, "commit": {"author": {"name": name, "date": "2026-05-01T10:00:00Z"}, "message": msg}, "author": {"login": name.lower()}}


def handler(request):
    path, q = request.url.path, dict(request.url.params)
    if request.url.host == "raw.githubusercontent.com":
        rel = path.split("/main/", 1)[1]
        return httpx.Response(200, text=FILES[rel]) if rel in FILES else httpx.Response(404)
    if path == "/repos/acme/shop":
        return httpx.Response(200, json={"full_name": "acme/shop", "default_branch": "main", "description": "A shop"})
    if path == "/repos/acme/shop/git/trees/main":
        return httpx.Response(200, json={"tree": [{"path": p, "type": "blob", "size": len(t)} for p, t in FILES.items()]})
    if path == "/repos/acme/shop/commits":
        if q["path"] == "billing":
            return httpx.Response(200, json=[commit("a", "Asha", "Add invoices"), commit("b", "Asha", "Fix tax"), commit("c", "Asha", "Add PDF")])
        if q["path"] == "cart":
            return httpx.Response(200, json=[commit("d", "Ben", "Add cart"), commit("e", "Asha", "Fix cart")])
        return httpx.Response(200, json=[commit("f", "Ben", "Write README")])
    if path == "/repos/acme/shop/issues":
        return httpx.Response(200, json=[
            {"number": 7, "title": "Refunds fail", "html_url": "https://github.com/acme/shop/issues/7", "user": {"login": "ben"}, "assignee": None, "updated_at": "2026-06-01T00:00:00Z"},
            {"number": 8, "title": "Add coupons", "html_url": "https://github.com/acme/shop/pull/8", "user": {"login": "asha"}, "assignee": None, "updated_at": "2026-06-02T00:00:00Z", "pull_request": {}},
        ])
    if path == "/repos/acme/gone":
        return httpx.Response(404, json={"message": "Not Found"})
    if path == "/repos/acme/limited":
        return httpx.Response(403, json={"message": "API rate limit exceeded"})
    return httpx.Response(500)


@pytest.fixture(autouse=True)
def fake_github(monkeypatch):
    real = httpx.Client
    monkeypatch.setattr(github_ingest.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


def test_snapshot_and_claims_from_a_repository():
    snap = fetch_snapshot("https://github.com/acme/shop")
    assert snap["repo"] == "acme/shop" and snap["modules"] == ["billing/", "cart/"]
    assert set(snap["files"]) == set(FILES)
    assert [i["is_pr"] for i in snap["issues"]] == [False, True]
    claims, facts = analyze([{"id": 1, "kind": "github", "name": "acme/shop", "visibility": "everyone", "content": json.dumps(snap), "meta": {}}])
    by = {c["title"]: c for c in claims}
    assert by["Asha is the main contributor to billing/"]["state"] == "verified"
    assert by["Only Asha knows billing/"]["evidence"][0]["url"].startswith("https://github.com/acme/shop/commit/")
    assert by["billing/ depends on cart/"]["evidence"][0]["url"].endswith("billing/invoice.py#L2")
    assert by["SHOP_KEY is not documented"]["state"] == "missing"
    assert by["SHOP_DB is needed to run billing/"]["state"] == "verified"
    assert by["README.md points to billing/missing.py, which does not exist"]["state"] == "conflicting"
    assert by["Open issue #7: Refunds fail"]["state"] == "verified"
    assert by["1 open issue has nobody assigned"]["state"] == "missing"
    assert facts["people"] == ["Asha", "Ben"]


def test_clear_errors_for_missing_repo_and_rate_limit():
    with pytest.raises(GitHubError, match="not found"):
        fetch_snapshot("acme/gone")
    with pytest.raises(GitHubError, match="rate limit"):
        fetch_snapshot("acme/limited")
    with pytest.raises(GitHubError):
        parse_repo("not a repo")


def test_module_picking_walks_through_wrapper_folders():
    assert pick_modules(["src/pkg/a.py", "src/pkg/b.py", "tests/test_a.py"]) == ["src/pkg/a.py", "src/pkg/b.py"]
    assert pick_modules(["api/x.py", "web/y.js", "docs/z.md"]) == ["api/", "web/"]
