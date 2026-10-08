# Publication webhooks

Admins add endpoints in Settings. Copy the one-time secret into the receiver;
it is never included in later reads or logs. Database backups contain secrets
and require the same protection as account/session data. Disable and recreate
an endpoint to rotate its secret. Up to ten active endpoints per workspace.

Each JSON body contains stable `id`, `event` (`published`, `unpublished`, `trashed`),
`workspaceId`, `typeKey`, `entryId`, `publicationRevision`, `slug`, `previousSlug`,
and `occurredAt`. It contains no content, draft title or private fields. Consumers
refetch delivery data and deduplicate by event ID for 30 days.
Verify `X-Moss-Signature` equals `sha256=` plus HMAC-SHA256(secret,
`X-Moss-Timestamp + "." + raw_body`), using constant-time comparison. Reject a
timestamp more than five minutes old. Retries have fresh timestamp/signature
but the same event ID. Accept duplicates with 2xx and no repeated side effect.

Public endpoints require HTTPS and global IPs. Every attempt resolves all DNS
addresses, validates them and pins the selected address for the connection;
TLS verifies the original hostname. Redirects are failures. No proxy environment
is used. `MOSS_WEBHOOK_ORIGINS` is an explicit comma-separated operator override
for trusted local origins, e.g. `http://personal-site:5174`; paths are not allowed
in that setting. It intentionally grants private-network access to those origins.

A separate worker fans out committed events, then performs network requests
outside write transactions. Claims expire after two minutes. At most six attempts
use 5s, 30s, 120s, 600s, 3600s backoff and a five-second socket timeout. Delivery
history shows the latest 100 records and safe error categories. Completed/failed
history and processed outbox events are pruned after 30 days; pending work is
retained until delivered or explicitly disabled. Restarting the API resumes work.
