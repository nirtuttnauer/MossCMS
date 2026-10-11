# MossCMS example site

A standalone **Vite + React + TypeScript** frontend for MossCMS. Desktop layout is exactly **20% sidebar / 80% main view**, with a dark `#11151B` sidebar. On small screens the sidebar becomes a header. Published CMS entries control navigation, projects, blog posts, page copy, colors, wording, and the rotating home showcase.

## Start locally

From this directory, with MossCMS running on port 8001, temporarily set
`MOSS_SKIP_AUTH=true` in the root `.env` and recreate the local app with
`docker compose up -d app` from the repository root. This setup shortcut is
available only in development. Then run:

```sh
python3 scripts/setup_moss.py --name "Moss Example"
npm ci
npm run dev
```

Open http://localhost:5174. The setup command creates a dedicated **Example website** workspace with five content types: **Projects**, **Blog posts**, **Website page**, **Homepage slide**, and **Website profile**. It supplies Home/Projects/Blog/About navigation pages, two sample projects (MossCMS and the example frontend), a starter blog post, and four showcase templates. Rerunning upgrades schemas and retains edits; older project/post pages are moved into their own types while preserving IDs, content, schedules and revision history. The earlier Notes/Contact navigation pages are renamed by ID. Automatic setup uses the CMS's temporary `MOSS_SKIP_AUTH=true` mode. After setup, restore `MOSS_SKIP_AUTH=false` in the root `.env` and run `docker compose up -d app` again. The resulting delivery token continues to work with normal authentication.

## Edit content

In [MossCMS](http://localhost:8001), select **Example website** in the workspace menu:

- **Website profile**: name, headline, introduction, email, location, social links, optional availability message, **Website colors**, **Website wording**, `carouselSeconds`, and `carouselAutoplay`. Colors use six-digit hex; invalid values fall back to defaults. The sidebar shows the editable brand and navigation; the remaining profile copy appears on the home and about pages.
- **Website page**: title, description, body, navigation order, page kind, parent slug, optional external URL/link label, and optional content cards.
- Top-level pages leave `parentSlug` empty. Their titles and `order` control the navigation. The home page uses `kind=home`; Projects uses `kind=projects`, Blog uses `kind=blog`, and About uses `kind=about` (with an email link when set in the profile).
- **Add a project**: select the **Projects** group and click **New project**. Enter a title, description, body, slug, and order. Publish it or schedule it. Published projects automatically appear in both the Projects listing and expandable sidebar list; selecting one opens its own page. No parent slug or page kind needs to be entered.
- **Add a blog post**: select **Blog posts** and click **New blog post**. Published posts automatically appear in Blog and become eligible for the blog showcase template. Posts scheduled for a future date stay private until then.
- Project and post entries automatically follow their navigation section even if its slug changes. Their routes are `/projects/<slug>` and `/blog/<slug>`, allowing a project and post to share a slug. Legacy hashes translate to these paths; unique current simple aliases redirect with 308. A published slug change releases the old path without retaining a historical redirect.
- Optional `items` lists add extra content cards to any page. Cards support title, description, URL, and link label.
- Publish changes to make them visible. New drafts and pending captures are private; editing or scheduling a live entry preserves its existing live version. Signed publication events invalidate the cache and notify connected browsers; ten-second/visibility polling remains available. During an outage, a marked stale public cache may persist for up to ten minutes.

Starter copy is editable. The setup uses generic sample content and leaves contact details and social accounts empty.

## Schedule posts

Open a blog post and select **Schedule** in the publishing panel. Choose **Publish on** in the displayed browser timezone and click **Schedule publication**. Scheduled dates appear in the library next to a blue Scheduled badge; the status filter lets you view the queue. Scheduling captures the selected revision; later draft edits do not change it. Use **Replace schedule** to include new edits and **Cancel schedule** to cancel without unpublishing. **Unpublish** explicitly removes live content and clears the schedule. Draft saves preserve both live content and the capture.

MossCMS publishes due entries approximately every 5 seconds and handles overdue entries after a restart. Keep the CMS running. Healthy signed events request an immediate website refresh; polling is the fallback. A published blog post joins the carousel after refresh. Failed captures appear in **Publications** and preserve existing live content; retry the retained capture or explicitly replace/discard it.

## Home showcase

Edit **Homepage slide** entries to choose the component, title, eyebrow, description, link, colors, speed, optional duration, and enabled state. Publish a slide to include it:

| Kind | Component |
| --- | --- |
| `liquid` | Canvas simulation of a damped liquid surface; pointer movement adds ripples. |
| `three` | A real Three.js scene with a rotating, lit torus knot. Three.js loads on demand; browsers without WebGL display a static geometric fallback. |
| `promotion` | A project highlight with editable copy and a link. Use `/projects/mosscms` for an internal page. |
| `blog` | A template for published blog posts. Each post supplies its title, excerpt and internal link; the template controls colors, eyebrow and link label. No published posts means no blog slides. |

The carousel shuffles the eligible slides, shows each once per cycle, and avoids repeating the same slide across cycle boundaries. New published blog posts join after the content refresh. You can add multiple slides of any kind. Component code lives in `src/components`; adding an entirely new animation kind requires a React component and a schema option, while all existing components are configured through MossCMS.

The profile's rotation interval defaults to 12 seconds (5–120 seconds); a slide's `duration` overrides it. Pause, next/previous and direct slide controls are included. Hovering or keyboard focus pauses rotation while the animation continues. Explicit pause, hidden tabs, offscreen views, and reduced-motion preferences stop the animations too. Reduced motion also disables automatic rotation.

## Connection and credentials

`.env` holds `MOSS_API_URL`, `MOSS_PROJECT_ID`, and **server-only** `MOSS_DELIVERY_TOKEN`. The token is scoped to the five website content types. No `VITE_` variables contain credentials. The browser reads `/api/site`; a server adapter makes one paginated, authenticated, published-only GraphQL request for the website content. This also avoids cross-origin browser configuration.

If authentication is enabled during initial setup, create the workspace/types/entries through MossCMS and create a delivery token in Settings with `siteProfile`, `sitePage`, `siteSlide`, `siteProject`, and `sitePost` scopes. The schema definitions are in `scripts/setup_moss.py`. Save the token to `.env` using `.env.example` as a guide. Expired or revoked tokens can be replaced there; restart the website after changing environment variables.

## Docker

From the MossCMS root:

```sh
docker compose --profile website up --build -d example-site
```

The website service uses port 5174 and connects to the app service internally. Your example-site `.env` must exist first. This service is optional and runs separately from the CMS admin.

## Production domain

The example defaults to **http://localhost:5174**. Set `SITE_PUBLIC_URL` in `.env` to your own HTTPS origin when deploying; canonical and social metadata use this value. The visible brand is editable in the profile's wording settings and starts as `Moss Example`. The local preview remains on port 5174.

Point the domain’s DNS at your hosting server and terminate HTTPS at a reverse proxy forwarding to `127.0.0.1:5174`. Domain configuration in this project does not update DNS or publish the site.


```sh
npm run build
npm start
```

The small Node server serves the Vite build and `/api/site`. Set `MOSS_API_URL` to your CMS origin and keep the delivery token in the server environment. Host behind HTTPS. A static-only host requires an equivalent server function for `/api/site`; a static upload alone will not provide the server adapter.

`npm run check` performs TypeScript checking. Both Vite development and preview include the same content adapter as the production server.

Markdown bodies use the same supported formatting and URL policy as the CMS preview.
Uploaded images use `![alt text](asset:ID)`; the server resolves fresh URLs only for
assets referenced by visible published fields. Missing images have a fallback.
Build the website image from the repository root with
`docker build -f example-site/Dockerfile -t moss-example-site .` so shared rendering policy is included.

Saved-draft previews use a 15-minute editor-issued capability and the website
server's existing delivery token. Its workspace/type scope must include the entry.
Open `/preview#grant=...` only through the admin preview control. The grant is
removed from the visible URL before redemption; a short-lived HttpOnly cookie
identifies an in-memory website session. Restarting the website ends sessions.
Every preview fetch revalidates expiry, revocation and editor access. Preview
responses are no-store/noindex and the persistent banner provides Exit preview.
Do not share preview links. `SITE_PREVIEW_ORIGINS` can list additional trusted
authoring origins; development defaults to `http://localhost:5174`. Production
`SITE_PUBLIC_URL` should use HTTPS so preview cookies are Secure.

Published pages use `/slug`, posts `/blog/slug`, and projects `/projects/slug`.
Normal links, refresh and browser back/forward work without a client router.
Legacy namespaced hashes and unique simple hashes are translated on load.
Only live slugs are routed. Publishing a slug change releases the old path;
there is no historical redirect retention. Unique current aliases redirect with
308. Unknown paths return an HTTP 404, and content outages return 503.

Each page's initial HTML contains its own escaped metadata and canonical URL,
based solely on `SITE_PUBLIC_URL`. Preview responses include noindex and no-store.
Optional `SITE_SOCIAL_IMAGE` must be a durable HTTPS URL without query or fragment
(or a path under the configured site). Signed asset URLs are never used as permanent
social images. Publish a static image for this setting; otherwise cards omit images.

Publication refresh: create a CMS webhook for this website's `/api/moss-events`.
Set its one-time secret as `MOSS_WEBHOOK_SECRET` and the workspace UUID as
`SITE_MOSS_WORKSPACE_ID` in the website environment. Allow the exact container
origin in API `MOSS_WEBHOOK_ORIGINS` for an internal HTTP callback. The receiver
checks timestamp, HMAC, workspace and event ID, then clears its public cache and
signals connected browsers over `/api/events`. Duplicate/out-of-order events
always refetch current state. Preview snapshots never enter the shared cache.
Public cache TTL is five seconds; browsers also poll every ten seconds and on
visibility changes. This refreshes 15-minute media links well before expiry.
During a delivery outage, the last valid public cache may be served for at most
ten minutes, marked stale. Preview authorization still fails closed. Cache and
signals are per process: configure a webhook per instance or use shared pub/sub
when scaling. Polling remains available if SSE or webhooks are unavailable.

For saved previews, conflicts, Markdown, covers and galleries, follow [editor workflows](../docs/editor-workflows.md). For exact Compose webhook environment, TLS/SSE proxying, backup/image pairing and provider limitations, use [deployment and recovery](../docs/deployment-recovery.md). [Release evidence](../docs/release-acceptance-2026-10-08.md) records actual local checks.
