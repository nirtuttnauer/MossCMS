# Client hardening

First paid setup for one MossCMS app process. Terminate TLS at a reverse proxy, send Content-Security-Policy and Strict-Transport-Security from that proxy, set explicit HTTPS origins, and keep secrets out of the repository.

This guide follows the loopback rehearsal in [reviews/MOSS-026/README.md](../reviews/MOSS-026/README.md). The header and browser checks for this page are in [reviews/MOSS-009/README.md](../reviews/MOSS-009/README.md). Nothing here registers a public name or changes hosting. `cms.moss.test` is a reserved `.test` name that resolves only through the rehearsal machine's `/etc/hosts`.

Live OAuth and S3 are not part of this offer. Leave `MOSS_GITHUB_CLIENT_ID`, `MOSS_GITHUB_CLIENT_SECRET`, `MOSS_OIDC_DISCOVERY_URL`, `MOSS_OIDC_CLIENT_ID`, `MOSS_OIDC_CLIENT_SECRET`, `MOSS_S3_BUCKET`, `MOSS_S3_ENDPOINT`, `AWS_ACCESS_KEY_ID`, and `AWS_SECRET_ACCESS_KEY` empty. Provider registration and a private bucket are a later scope. See [OAuth setup](oauth-setup.md) only when that scope is in the contract.

## One app process

Run a single app process. Do not add a second container, a second host, or `uvicorn` workers.

Setup, sign-in, and invitation acceptance are rate limited in that process. `api/app/main.py` stores the counters on `app.state.login_attempts`, an ordinary dictionary created when the process starts. `api/app/accounts.py` (`rate_limit`) keeps the last attempts for each key, allows 8 in a 60-second window, and returns 429 after that. The keys are the client address prefixed with `setup:`, `login:`, or `accept:`. The dictionary is not in PostgreSQL, Redis, or a shared volume. A second process has its own empty map, so the limit does not hold across instances. Restarting the process clears it.

This limit applies with PostgreSQL as well as SQLite. SQLite already has to stay on one process because the database file is local. PostgreSQL does not remove this limit. The image command (`python -m app.cli serve`) starts one Uvicorn process and does not set a worker count. Leave it that way. The Compose `app` service stays at one replica.

The optional example website also keeps its cache and SSE sessions in process memory. That is a separate limit, described in [deployment and recovery](deployment-recovery.md). It is not a reason to run more than one CMS process.

## Secrets

Generate configuration from the repository root. Do not invent a secret and paste it into a committed file.

```sh
python3 scripts/configure.py --production --public-url https://cms.example.com
```

`--production` refuses a public URL that is not HTTPS. The command writes `.env` with mode `0600`. It generates `POSTGRES_PASSWORD`, `MOSS_SECRET_KEY` (32+ characters), and `MOSS_SETUP_TOKEN` (24+ characters) when those keys are missing, and it does not print the values. `.env` is gitignored. `.env.example` contains placeholders only.

Keep these off the repository, out of images, and out of tickets:

- `.env` and `example-site/.env`
- `MOSS_SECRET_KEY`, `MOSS_SETUP_TOKEN`, `POSTGRES_PASSWORD`
- delivery tokens and webhook signing secrets
- TLS private keys and the private key of any private CA
- OAuth client secrets and cloud storage credentials, when a later offer uses them

Changing `MOSS_SECRET_KEY` invalidates pending OAuth state and signed media links. For a database that already exists, changing `.env` does not rotate the PostgreSQL role password: change the role through an operator connection and update `.env` together. Backups contain account and session data. Store them with the matching `.env` in private encrypted storage, not in git.

The rehearsal records in this repository do not contain those values. The TLS key for the check stayed on the machine under `/tmp` and is not in the tree.

## Origins

The browser origin is the proxy's HTTPS origin, not the loopback port.

| Setting | Value for one admin on the proxy |
| --- | --- |
| `MOSS_ENV` | `production` |
| `MOSS_SKIP_AUTH` | `false` |
| `MOSS_PUBLIC_URL` | `https://cms.example.com` (include a non-default port, as the rehearsal did with `:8443`) |
| `MOSS_ORIGINS` | That same origin. `scripts/configure.py --production` sets this to the public URL alone |
| `MOSS_BIND_HOST` | `127.0.0.1` (the default) |
| `MOSS_PORT` | `8001` unless the host port in front of the container must move. The proxy still targets the published loopback port |

`MOSS_ORIGINS` is an explicit comma-separated list. `*` is rejected at startup. Do not add the loopback URL `http://127.0.0.1:8001`. Browsers never send that as `Origin` when they are on the HTTPS proxy. A request whose `Origin` is not in the list is rejected with 403 for every method other than `GET`, `HEAD`, and `OPTIONS`.

In production the session cookie is `Secure`, and the OAuth session middleware is HTTPS-only. A website preview origin saved in workspace Settings must be `https` (no path, query, user, or password). Production OIDC discovery, if a later offer enables it, must be `https`.

`MOSS_WEBHOOK_ORIGINS` is not a browser list. It is the allowlist for server-to-server callbacks on private addresses. The Compose website uses `http://example-site:5174`. Leave it empty when there is no website callback.

The rehearsal used `MOSS_PUBLIC_URL=https://cms.moss.test:8443` and `MOSS_ORIGINS=https://cms.moss.test:8443`.

## TLS, CSP, and HSTS at the proxy

The app listens on `127.0.0.1:8001` and does not terminate TLS. The proxy listens on HTTPS, forwards to that port, and adds the two headers below.

The app already sends `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, and `X-Frame-Options: DENY` (`api/app/main.py`). Leave those in place. `frame-ancestors 'none'` agrees with `X-Frame-Options: DENY`.

On the rehearsal host the proxy is nginx 1.24. The CMS server is:

```nginx
server {
  listen 127.0.0.1:8443 ssl;
  server_name cms.example.com;
  ssl_certificate /path/to/fullchain.pem;
  ssl_certificate_key /path/to/privkey.pem;
  ssl_protocols TLSv1.2 TLSv1.3;
  add_header Strict-Transport-Security "max-age=300" always;
  add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'; upgrade-insecure-requests" always;

  location / {
    proxy_pass http://127.0.0.1:8001;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Host $host:$server_port;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header Connection "";
  }
}
```

Use the client's certificate paths and server name. The checked file, with the rehearsal paths, is [reviews/MOSS-009/rehearsal/nginx.conf](../reviews/MOSS-009/rehearsal/nginx.conf). It follows the MOSS-026 proxy: TLS 1.2 and 1.3, `X-Forwarded-Proto https`, and an access log that records method, path, and status and does not record cookies, authorization, or bodies.

`add_header` on a `location` replaces server-level `add_header` lines. Any location that sets its own headers must repeat both lines. `always` keeps the headers on error responses.

`Strict-Transport-Security: max-age=300` is the value this offer checks. Five minutes is enough to prove the proxy sends HSTS, and it is short enough that a mistake on a new name expires quickly. Do not add `includeSubDomains` or `preload` in this offer. After the curl check below passes on the permanent HTTPS name, raise `max-age` (180 days is `15552000`). Do that only when every browser that will use the name should keep using HTTPS.

The Content-Security-Policy value is the one the admin UI loaded with zero policy violations:

```
default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'; upgrade-insecure-requests
```

The production admin is one same-origin document. Its scripts and styles are `/assets/` files. `web/src/style.css` imports the DM Sans, DM Mono, and Manrope stylesheets from `https://fonts.googleapis.com`, and those stylesheets load font files from `https://fonts.gstatic.com`. Both hosts are in the policy for that reason. There is no `'unsafe-inline'` and no `'unsafe-eval'`.

`img-src 'self'` allows the brand marks and local media on the CMS origin. It does not allow an image URL on another host, including a Markdown image that points off-origin and an S3 presigned URL. This offer stores media on the local volume, so editor and library images stay on the CMS origin. A later S3 offer has to name that host in `img-src` before those URLs will render.

`connect-src 'self'` allows the admin's calls to `/auth`, `/api`, and `/graphql` on the proxy origin. It does not allow a browser call to another host.

## Check the headers with curl

From the rehearsal host, or from a client machine that trusts the proxy certificate:

```sh
curl -I --cacert /path/to/ca.crt https://cms.example.com/
curl -sS -D - -o /dev/null --cacert /path/to/ca.crt https://cms.example.com/ready
```

Drop `--cacert` when the certificate is publicly trusted. `curl -I` sends `HEAD`.

`HEAD /` returns 200. The response includes:

| Header | Value |
| --- | --- |
| `Strict-Transport-Security` | `max-age=300` |
| `Content-Security-Policy` | the policy in the previous section |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `same-origin` |
| `X-Frame-Options` | `DENY` |

`GET /ready` returns 200 and `{"status":"ready"}`, with the same proxy headers. `/ready` is registered for `GET`, so `curl -I https://cms.example.com/ready` is `405` with `allow: GET`. The proxy still attaches both headers because of `always`. Use the `GET` command above when the body matters.

The recorded `curl -I` of the admin document is [reviews/MOSS-009/rehearsal/admin.headers](../reviews/MOSS-009/rehearsal/admin.headers). The recorded `GET /ready` headers are [ready.headers](../reviews/MOSS-009/rehearsal/ready.headers).

## Check the admin console

Open the HTTPS origin in a browser. The sign-in page (or the first-administrator form, before setup) is the admin UI. Open the console before interacting.

A CSP failure is a message that contains `Content Security Policy` or `Refused to`, or a `securitypolicyviolation` event. The checked policy produced none of those on:

- the sign-in page, including the brand images and the Google font files
- Content, Overview, Import & export, API explorer, Settings, and Assets after sign-in

Import & export is a separate script (`/assets/Migration-*.js`). It has to load from the same origin under `script-src 'self'`.

Before sign-in, `GET /auth/me` returns 401. The console reports that as a failed resource load. That line is the signed-out session check. It is not a CSP violation. After a successful sign-in the same request returns 200.

Screenshots of the sign-in page and the content library, taken with the policy enabled, are in [reviews/MOSS-009/rehearsal/](../reviews/MOSS-009/rehearsal/).
