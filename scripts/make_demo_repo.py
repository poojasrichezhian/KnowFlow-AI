"""Builds the sample repository used by the bundled demo project.

Fictional team, fixed dates -> the commit SHAs are identical on every run, so the
snapshot in backend/seed/ always matches the repo once you push it to GitHub.

    python scripts/make_demo_repo.py ./payments-service-demo
"""
import os, subprocess, sys, shutil

A = ("Arjun Sharma", "arjun.sharma@example.com")
M = ("Meera Nair", "meera.nair@example.com")
R = ("Rohan Iyer", "rohan.iyer@example.com")

README_V1 = """# Payments Service

Handles checkout payments, gateway webhooks and customer notifications.

## Modules

- `payments/` - payment API and gateway client
- `webhooks/` - gateway webhook receiver
- `auth/` - service token validation
- `notifications/` - customer notification queue
- `db/` - schema and migrations

## Configuration

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection string |
| `PAYMENT_GATEWAY_KEY` | API key for the payment gateway |

## Running

    pip install -r requirements.txt
    python -m payments.api
"""

README_V2 = README_V1.replace(
    "## Configuration",
    "## Retries\n\nFailed gateway calls are retried asynchronously by the retry worker in\n`workers/retry_worker.py`, so checkout requests are never blocked.\n\n## Configuration",
)

ARCH = """# Architecture notes

The Payment API validates every request with the Auth Service before calling the gateway.
Webhook events from the gateway are stored and then pushed to the notification queue.

Meera maintains the webhooks module.

The notification queue is an in-process queue for now.
"""

API_V1 = '''"""Payment API: creates charges for checkout."""
import os

from auth.tokens import validate_token
from payments.gateway import charge

DATABASE_URL = os.environ["DATABASE_URL"]


def create_payment(token, order_id, amount_paise):
    """Validate the caller, then charge the gateway once."""
    validate_token(token)
    return charge(order_id, amount_paise)


if __name__ == "__main__":
    print("payments service ready")
'''

API_V2 = API_V1.replace(
    "from payments.gateway import charge\n",
    "from payments.gateway import charge\nfrom payments.retry import with_retry\nfrom notifications.queue import enqueue\n",
).replace(
    '    """Validate the caller, then charge the gateway once."""\n    validate_token(token)\n    return charge(order_id, amount_paise)\n',
    '    """Validate the caller, charge the gateway with retries, then notify the customer."""\n    validate_token(token)\n    result = with_retry(lambda: charge(order_id, amount_paise))\n    enqueue("payment_succeeded", {"order_id": order_id})\n    return result\n',
)

GATEWAY = '''"""Thin client for the payment gateway."""
import os

GATEWAY_KEY = os.environ["PAYMENT_GATEWAY_KEY"]
RATE_LIMIT_PER_SECOND = 40


class GatewayError(Exception):
    pass


def charge(order_id, amount_paise):
    # FIXME: gateway returns HTTP 200 with an error body for declined cards; we only check the status code
    return {"order_id": order_id, "amount": amount_paise, "status": "captured"}
'''

RETRY_V1 = '''"""Retry helper for gateway calls.

Retries run synchronously inside the request and block the checkout call until they finish.
"""
import time

MAX_ATTEMPTS = 3


def with_retry(fn):
    last = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(2 ** attempt)
    raise last
'''

RETRY_V2 = RETRY_V1.replace(
    "import time\n\nMAX_ATTEMPTS = 3\n",
    'import os\nimport time\n\nMAX_ATTEMPTS = int(os.environ.get("RETRY_MAX_ATTEMPTS", "3"))\n',
).replace(
    "            time.sleep(2 ** attempt)\n",
    "            # HACK: sleep is capped at 4s because the load balancer drops requests after 10s\n            time.sleep(min(2 ** attempt, 4))\n",
)

WEBHOOK_V1 = '''"""Receives webhook events from the payment gateway."""
import hashlib
import hmac
import os

WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]


def verify_signature(body, signature):
    expected = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def handle_event(body, signature):
    if not verify_signature(body, signature):
        raise PermissionError("bad webhook signature")
    return {"received": True}
'''

WEBHOOK_V2 = WEBHOOK_V1.replace(
    'import os\n\nWEBHOOK_SECRET',
    'import os\n\nfrom db.migrations import save_event\nfrom notifications.queue import enqueue\n\nWEBHOOK_SECRET',
).replace(
    '    return {"received": True}\n',
    '    # TODO: reject events older than 5 minutes to stop replay attacks\n    save_event(body)\n    enqueue("webhook_received", {"size": len(body)})\n    return {"received": True}\n',
)

TOKENS = '''"""Service-to-service token validation."""
import os

AUTH_PUBLIC_KEY = os.environ.get("AUTH_PUBLIC_KEY", "")


def validate_token(token):
    if not token:
        raise PermissionError("missing token")
    return True
'''

QUEUE = '''"""In-process notification queue."""
from collections import deque

_queue = deque()


def enqueue(event, payload):
    _queue.append((event, payload))


def drain():
    while _queue:
        yield _queue.popleft()
'''

SCHEMA_V1 = """CREATE TABLE payments (
    id SERIAL PRIMARY KEY,
    order_id TEXT NOT NULL,
    amount_paise INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE webhook_events (
    id SERIAL PRIMARY KEY,
    body BYTEA NOT NULL,
    received_at TIMESTAMP DEFAULT now()
);
"""

MIGR_V1 = '''"""Database helpers and migrations."""


def save_event(body):
    return True
'''

MIGR_V2 = MIGR_V1 + '''

def migrate_refunds_table():
    # TODO: refunds table migration is half done - backfill of old refunds not written yet
    raise NotImplementedError("refunds backfill pending")
'''

TEST_API = '''from payments.retry import with_retry


def test_with_retry_returns_value():
    assert with_retry(lambda: 1) == 1
'''

REQS = "requests\npsycopg2-binary\n"

COMMITS = [
    (A, "2026-03-02T10:00:00", "Initial payment API and gateway client",
     {"README.md": README_V1, "requirements.txt": REQS, "payments/__init__.py": "", "payments/api.py": API_V1,
      "payments/gateway.py": GATEWAY.replace("RATE_LIMIT_PER_SECOND = 40", "RATE_LIMIT_PER_SECOND = 100")}),
    (M, "2026-03-05T11:30:00", "Add service token validation",
     {"auth/__init__.py": "", "auth/tokens.py": TOKENS}),
    (A, "2026-03-12T09:15:00", "Add database schema for payments and webhook events",
     {"db/schema.sql": SCHEMA_V1, "db/__init__.py": "", "db/migrations.py": MIGR_V1}),
    (A, "2026-03-20T16:40:00", "Add webhook receiver with signature check",
     {"webhooks/__init__.py": "", "webhooks/handler.py": WEBHOOK_V1}),
    (M, "2026-03-27T14:00:00", "Write architecture notes",
     {"docs/architecture.md": ARCH}),
    (A, "2026-04-08T10:20:00", "Add retry helper for gateway calls",
     {"payments/retry.py": RETRY_V1}),
    (A, "2026-04-10T12:00:00", "README: describe retries and the planned retry worker",
     {"README.md": README_V2}),
    (R, "2026-04-22T15:10:00", "Add in-process notification queue",
     {"notifications/__init__.py": "", "notifications/queue.py": QUEUE}),
    (A, "2026-05-06T09:45:00", "Use retry helper in payment API and notify on success",
     {"payments/api.py": API_V2}),
    (A, "2026-05-19T17:05:00", "Store webhook events and push them to notifications",
     {"webhooks/handler.py": WEBHOOK_V2}),
    (M, "2026-06-03T10:30:00", "Add first test for the retry helper",
     {"tests/test_api.py": TEST_API}),
    (A, "2026-06-24T13:20:00", "Lower gateway rate limit to 40 requests per second",
     {"payments/gateway.py": GATEWAY}),
    (A, "2026-07-15T11:00:00", "Make retry attempts configurable and cap backoff",
     {"payments/retry.py": RETRY_V2}),
    (R, "2026-08-04T16:00:00", "Notification queue: note that events are lost on restart",
     {"notifications/queue.py": QUEUE.replace('"""In-process notification queue."""', '"""In-process notification queue. Events are lost on restart."""')}),
    (A, "2026-09-09T10:10:00", "Start refunds table migration",
     {"db/migrations.py": MIGR_V2,
      "db/schema.sql": SCHEMA_V1 + "\nCREATE TABLE refunds (\n    id SERIAL PRIMARY KEY,\n    payment_id INTEGER REFERENCES payments(id),\n    amount_paise INTEGER NOT NULL\n);\n"}),
    (A, "2026-10-01T15:30:00", "Webhook handler: tighten signature error message",
     {"webhooks/handler.py": WEBHOOK_V2.replace("bad webhook signature", "invalid webhook signature")}),
]


def run(cwd, *args, env=None):
    subprocess.run(args, cwd=cwd, check=True, env=env, stdout=subprocess.DEVNULL)


def main(dest):
    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)
    run(dest, "git", "init", "-q", "-b", "main")
    for (name, email), date, msg, files in COMMITS:
        for path, content in files.items():
            full = os.path.join(dest, path)
            os.makedirs(os.path.dirname(full) or dest, exist_ok=True)
            with open(full, "w", newline="\n") as fh:
                fh.write(content)
        env = dict(os.environ, GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email, GIT_COMMITTER_NAME=name,
                   GIT_COMMITTER_EMAIL=email, GIT_AUTHOR_DATE=date + "+0530", GIT_COMMITTER_DATE=date + "+0530")
        run(dest, "git", "add", "-A", env=env)
        run(dest, "git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", msg, env=env)
    print(f"Created {dest} with {len(COMMITS)} commits")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "payments-service-demo")
