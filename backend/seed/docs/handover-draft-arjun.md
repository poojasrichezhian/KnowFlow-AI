# Handover draft - Arjun Sharma (last working day 14 Nov 2026)

- The Payment API depends on the auth module to validate tokens before every charge.
- Declined cards are a known issue: the gateway returns HTTP 200 with an error body and we only check the status code.
- The retry backoff is capped at 4 seconds as a workaround for the load balancer timeout.
- Pending: replay protection for webhook events is not started.
- Meera is responsible for the auth module.
