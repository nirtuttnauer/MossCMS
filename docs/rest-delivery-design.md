# REST delivery design

**Status: approved by CTO (Oct 29, 2026).** Architecture draft, 29 October 2026. QA writes the final acceptance criteria.

This fixes the REST path, auth, and caching choices before implementation. It describes behavior already implemented for delivery GraphQL at `3a87c73` (`api/app/main.py`, `api/app/security.py`, `api/app/content.py`, `api/app/graphql.py`, `api/app/schema.py`, `api/app/ordering.py`). That delivery code is unchanged at `b306d3f`. The publication rules are the ones in [publication-contract.md](publication-contract.md).

## Prefix

Readable delivery REST lives under `/delivery`.

`POST /graphql` and `POST /delivery/graphql` are the only content reads today (`create_app` in `api/app/main.py`). The HTTP middleware sets `Cache-Control: no-store` on every path that starts with `/auth` or `/api`, after the handler returns. A handler under those prefixes cannot keep a cache policy. `/delivery` is the prefix that already means "delivery token" (`request.url.path.startswith("/delivery/")`) and the prefix whose successful GraphQL responses set an ETag and return 304.

Token administration stays on `/api/tokens`. Preview redemption stays on `POST /api/preview/redeem`, which already sends `Cache-Control: no-store` and can return an unpublished revision. Those routes stay out of the cacheable prefix.

## Paths

GET and HEAD only. Any other method is 405. `POST /delivery/graphql` stays as it is.

| Path | Calls |
| --- | --- |
| `/delivery/types` | The `content_types` selection: project types, ordered by name, scope filter, `public_fields` |
| `/delivery/types/{typeKey}` | `content.get_type`, then `public_fields` |
| `/delivery/entries` | `content.entry_page` |
| `/delivery/entries/{id}` | `content.get_entry`, then `content.entry_dict` |
| `/delivery/entries/{id}/resolved-assets` | `resolved_image_assets` on the published snapshot, as `EntryNode.resolved_assets` does |
| `/delivery/website/redirects` | `content.website_redirects` |
| `/delivery/website/reserved-paths` | `content.website_reserved_paths` |

Each handler opens a session the way the GraphQL route does, then:

```text
identify(request, session, delivery=True)
require(context)
```

The context passed to those functions carries `session`, `settings`, and `request`, same as the GraphQL handler. The route then calls the function in the table. It does not add a second query, a slug lookup, or a status filter.

There is no by-slug path. Delivery GraphQL has no slug field resolver. `GET /delivery/entries` search is the existing substring match. Website canonical paths are the two website routes, which the example site already reads through delivery GraphQL.

### Bodies

Entry JSON is the dict `entry_dict` returns for a delivery identity, null keys included. There is no field selection on REST, so the document is the whole dict: `id`, `typeKey`, `slug`, `title`, `data`, `status`, `version`, `updatedAt`, `scheduledAt`, `isLive`, `hasUnpublishedChanges`, `publishedAt`, `publishedRevision`, `scheduledRevision`, `scheduleError`, `publishedData`, `publishedSlug`, `publishedTitle`, `publishedSnapshot`.

The list body is the dict `entry_page` returns, without `totalQuery` (that value is a SQL statement, not JSON):

```json
{ "nodes": [], "endCursor": null, "hasNextPage": false }
```

`total` is added only when the request sets `total=true`. Otherwise the handler passes `include_total=False`, which is what the GraphQL `entries` resolver passes, and omits `total`.

A type document is `{ "id", "key", "name", "fields", "version" }` with `fields` replaced by `public_fields`. The list uses the same scope rule as `content_types`: an empty scope list returns every type in the token's project; a non-empty list keeps only those keys. `entry_count` stays a GraphQL selection. A count is `GET /delivery/entries?typeKey={key}&total=true&first=1`.

`/delivery/website/redirects` and `/delivery/website/reserved-paths` return the values of those functions unchanged. Reserved paths are path strings. Redirects are the `{ "from", "to", "entryId" }` objects `website_redirects` builds, and only for entries that are live and inside the token scopes.

`/delivery/entries/{id}/resolved-assets` returns a list of `{ "id", "name", "mime", "size", "url", "width", "height", "variants" }`. `variants` is the list `variant_metadata` already builds (`width`, `height`, `size`, `url`). The helper reads `published_data` because the context is a delivery context, keeps image MIME types, and stops at the 50 ids `image_asset_ids` keeps. Assets are limited to the token's project.

`data` on an entry is `public_data` of `published_data`. With no `locale` parameter, localized values stay maps of locale to value. `locale` on the list and on `GET /delivery/entries/{id}` selects that code from every localized public field, including fields nested in objects and lists. The lookup is the one a GraphQL field `locale` argument uses: the value at that key, or null when the key is absent. There is no fallback to the workspace default or to `en`. Reference and asset fields stay ids. REST does not expand references. A client that needs a referenced entry calls `GET /delivery/entries/{id}`.

### Query parameters

`/delivery/entries` accepts only the parameters below. `GET /delivery/entries/{id}` accepts only `locale`. Every other parameter on those routes, and every parameter on the other delivery routes, is HTTP 422 with `{"detail": "Unknown delivery parameter.", "code": "VALIDATION"}`. The handler rejects the request before it calls `entry_page`. `status`, `snapshot`, `slug`, and `scheduledAt` are unknown parameters.

| Parameter | Rule |
| --- | --- |
| `typeKey` | Optional. Passed through. An unknown key, or a key outside the token scopes, is `Content type not found.` (404) from `get_type`. |
| `search` | Optional. Passed through. `entry_page` matches the first 100 characters against `published_title` and `published_slug`. A private `title` does not match. |
| `sort` | Optional. Default `updated_desc`. Allowed values: `updated_desc`, `updated_asc`, `title_asc`, `title_desc`. For a delivery identity, `updated_*` orders by `published_at`. `title_*` uses `delivery_title`: the published slug when the type's `title` field is private, otherwise `published_title`. |
| `first` | Optional integer. Default 20. Range 1–100. A non-integer is 422 `Use a page size of 1–100 and a supported sort order.` The handler does not pass a string into `entry_page`. |
| `after` | Optional. The previous `endCursor`, returned unchanged as the cursor argument. |
| `filters` | Optional JSON object. Parsed and passed through. `entry_page` requires `typeKey`, allows at most ten fields, and allows only a visible non-localized scalar (`text`, `richText`, `number`, `boolean`, `date`, `enum`). Private fields raise `Filter on a visible scalar field.` Values are compared to `published_data` through the `published` field index. Numbers and booleans stay JSON numbers and booleans. A value that is not a JSON object, or that `entry_page` rejects, is 422. |
| `orderBy` | Optional field name. Requires `typeKey`. Combined with a `sort` other than `updated_desc`, `entry_page` raises `Field ordering requires a content type; use either sort or orderBy.` The field must be a visible non-localized scalar on the published index. A private field raises `Order by a visible, non-localized scalar field.` |
| `direction` | `asc` or `desc`, and only together with `orderBy`. Default `asc`, which is `OrderDirection.ASC`. Any other spelling is 422. |
| `total` | `true` or `false`. Default `false`. `true` passes `include_total=True` and adds `total` to the body. |
| `locale` | Optional. A stored locale code: `en`, `he`, `en-US`. Applied to `data` after the page is read. Omitted, the locale maps are unchanged. Any other spelling is 422 `Use a valid locale code.` Order, cursors, filters, search, and `total` ignore it. The same parameter on `GET /delivery/entries/{id}` projects that one document. |

Generated `allCms{Type}` lists drop the cursor. REST does not. The list route returns `endCursor` and `hasNextPage` from `entry_page`.

### Signed media URLs

`media_url` sets `expires` to the current time plus 900 seconds. Variant URLs do the same. Those URLs are absent from `/delivery/types`, `/delivery/entries`, and `/delivery/entries/{id}`. An ETag over a body that contains them would change on every request. `/delivery/entries/{id}/resolved-assets` is the place they are returned, and that route sends `Cache-Control: no-store`, no `ETag`, and never 304. A `resolvedAssets` query parameter is an unknown parameter, not a mode switch on the cached routes.

### Routes that are not added

Delivery GraphQL already refuses these. REST has no path for them.

| Surface | Delivery GraphQL today | REST |
| --- | --- | --- |
| `revisions` | HTTP 200, `extensions.code` `FORBIDDEN`, `Revision history is editorial only.` | 403, same `detail` and `code` |
| `assets`, `asset_page` | HTTP 200, `FORBIDDEN`, `Use an asset field on published content.` | 403, same `detail` and `code` |
| `publication_queue` | HTTP 200, `FORBIDDEN`, `Publication queues are editorial only.` | 403, same `detail` and `code` |
| `overview` | HTTP 200, `FORBIDDEN`, `Overview is editorial only.` | 403, same `detail` and `code` |
| `content_groups` | HTTP 200, `FORBIDDEN`, `Content groups are editorial only.` | 403, same `detail` and `code` |
| `seo_audit`, `seo_entry_audit` | HTTP 200, `FORBIDDEN`, `SEO audits are editorial only.` | 403, same `detail` and `code` |
| `audit_log`, `schema_history` | HTTP 200, `FORBIDDEN`, `Insufficient project permissions.` (`require` asks for admin; a delivery token is a reader) | 403, same body |
| `draft_receipt` | HTTP 200, `FORBIDDEN`, `Insufficient project permissions.` (`require` asks for editor) | 403, same body |
| Mutations | The delivery schema is built with `mutation=None`, so the document fails validation. `require(..., write=True)` raises `Delivery tokens cannot write content.` | No write route. A write flag on `require` is 403 with that `detail` and `code` |

GraphQL query-depth and selection limits apply to GraphQL documents. REST does not run `bounded_query`. Page size, filter cardinality, and cursor checks in `entry_page` and `field_page` are the bounds.

Request logging stays the middleware log: method, path, status, request id. The path does not include the query string. The handler does not log `Authorization` or the token.

## Auth

`identify(request, session, delivery=True)` is the whole check.

- `MOSS_SKIP_AUTH` does not authenticate delivery. The development short-circuit runs only when `skip_auth` is set and `delivery` is false.
- The credential is the raw delivery token. `Authorization: Bearer <token>` wins when the header starts with `Bearer `. Otherwise `identify` reads the `moss_session` cookie. Clients send the bearer header. A session token, an expired token, or a missing token is rejected because `kind` must be `delivery` and `expires_at` must be in the future. The stored id is the SHA-256 hex digest of the raw token.
- The token is not accepted from the query string. `identify` does not read it.
- The workspace is `token.project_id`. `X-Moss-Project` is not consulted. `scoped` filters every read by that project id.
- The delivery context is `delivery: True`, `role: "reader"`, `scopes` from the token, and `actor` set to the token name. There is no user and no CSRF secret. Reads call `require(context)` with the default reader role. A write flag raises `Delivery tokens cannot write content.`
- An empty `scopes` list means every content type in the project. The checks in `content_types`, `get_type`, and `entry_page` use `not scopes` for that. A non-empty list is an allow-list of type keys. Creating a token (`POST /api/tokens`, admin, CSRF) already rejects unknown keys.

A failed identify is HTTP 401, body `{"detail": "A valid delivery token is required."}`, which is the existing `HTTPException` shape and has no `code` field.

CORS already allows `GET`, allows the `If-None-Match` request header, and exposes `ETag`. The untrusted-origin rejection applies to methods other than `GET`, `HEAD`, and `OPTIONS`. The delivery token is the authorization check. Login rate limits stay on setup, login, and invitation accept. These routes do not add one.

## Errors

REST uses the status codes the app already maps. It does not return HTTP 200 with a GraphQL `errors` array.

The `CmsError` handler returns `{"detail": "<message>", ...extensions()}`. `extensions()` always includes `code`, and includes `fieldPath` and `reason` when the error has them. Status is 403 for `FORBIDDEN`, 404 for `NOT_FOUND`, 409 for `CONFLICT`, and 422 for every other code, including `VALIDATION` and `QUERY_LIMIT`.

| Situation | Status | Body |
| --- | --- | --- |
| Missing, expired, or non-delivery credential | 401 | `{"detail": "A valid delivery token is required."}` |
| `FORBIDDEN`, including a delivery write | 403 | `detail` plus `code` |
| `NOT_FOUND` | 404 | `detail` plus `code` |
| `CONFLICT` | 409 | `detail` plus `code` |
| Validation, bad cursor, bad page size, unknown parameter | 422 | `detail` plus `code` |
| Invalid `Content-Length` | 400 | `{"detail": "Invalid Content-Length."}` |
| Body over the configured limit | 413 | `{"detail": "Request body is too large."}` |
| Untrusted browser `Origin` on a non-safe method | 403 | `{"detail": "Untrusted browser origin."}` |
| Unhandled exception | 500 | `{"detail": "The request could not be completed.", "code": "INTERNAL"}` |

`X-Request-ID` is on every response, including 304 and 401. GraphQL also copies it into `extensions.requestId`. REST HTTP bodies do not; the header is the id, as on the other non-GraphQL routes.

Delivery visibility errors from the current helpers:

- Unknown id, another project, no live snapshot, or `status == "deleted"`: `get_entry` raises `Entry not found.` Those cases share one sentence.
- A live entry whose type is outside the token scopes: `get_entry` then calls `get_type`, which raises `Content type not found.` REST returns that error as the helper raises it.
- A list with `typeKey` outside the scopes is the same `Content type not found.` A list with no `typeKey` and a non-empty scope adds `type_id IN (scoped types)` and omits the other types.
- A malformed or oversized cursor is `Invalid page cursor.` `entry_page` rejects the default cursor above 1000 characters; `field_page` rejects an `orderBy` cursor above 1 MiB.

On success the handler commits the session, as the GraphQL route does. On failure it rolls the session back. Read routes do not call `require` with a write flag.

## Pagination

`entry_page` is the pager.

- `first` defaults to 20 and is an integer from 1 to 100. The query reads `first + 1` rows. `hasNextPage` is true when that extra row exists. `nodes` is the first `first` rows.
- With no `orderBy`, the sort key is `published_at` or the delivery title, then `id`, in the requested direction. `endCursor` is the cursor `entry_page` already encodes: URL-safe base64 of JSON `[value, id, sort]`. The `sort` stored in the cursor has to match the requested sort. A timestamp value is parsed with `datetime.fromisoformat`. Clients send that string back as `after` and do not build their own.
- `endCursor` is null when the page has no rows. It is set when the page has a row, including the last page. Clients stop when `hasNextPage` is false. `locale` does not change the cursor or the page membership. It only replaces localized values inside `data`.
- `orderBy` uses `ordering.field_page` on the `published` snapshot index. Nulls sort in a separate tail. That cursor is a different opaque string (URL-safe base64 of `{"scope", "id", "null", "value"}`). `scope` binds the project, type, field, field type, snapshot `published`, and direction. Clients treat it as opaque. The response still calls it `endCursor`.
- `total`, when requested, is the count `entry_page` computes for the same filter, including the published field index. The default list does not compute it.

## Caching

Successful list, entry, type, and website responses reuse the delivery GraphQL cache block in `create_app`: `Cache-Control`, `Vary`, `ETag`, and 304. MOSS-031 should turn that block into one helper used by the GraphQL route and these routes. The behavior of the block is:

- Success sends `Cache-Control: private, no-cache` and `Vary: Authorization, Origin`.
- The strong ETag is a quoted SHA-256 hex digest of `json.dumps(payload, sort_keys=True)` encoded as UTF-8, with the library default `ensure_ascii` and separators. It is a hash of that canonical dump, not a hash of the `JSONResponse` bytes. Clients compare the header. The helper keeps this dump.
- `If-None-Match` matches only when the header value equals that quoted digest. `*`, a weak validator (`W/"..."`), and a list of validators do not match. REST uses the same comparison. A parser that accepts those forms has to change the GraphQL route and the REST routes together.
- A match returns 304, an empty body, and the success `Cache-Control`, `Vary`, and `ETag`. The 304 carries no content type.
- HEAD hashes the same payload as GET. The hash is not taken from the empty HEAD body. A matching `If-None-Match` on HEAD is also 304.
- Every resolved-asset response, and every status other than 200 or 304, sends `Cache-Control: no-store` and `Vary: Authorization, Origin`, omits `ETag`, and does not return 304. The global `CmsError` handler and the `/auth`/`/api` middleware do not set this on a `/delivery` path, so the delivery route sets it on the response it returns, including the 401 from `identify`. The JSON body stays the body documented above.
- An empty list is a 200 and is cached.
- `private` keeps a shared cache from storing a body that depends on the token's scopes. `no-cache` means a cache revalidates with the ETag before reuse. The headers do not include `public`, `max-age`, `s-maxage`, or `Last-Modified`.

`test_delivery_scopes_drafts_private_fields_cache_and_revocation` already requires that repeating `If-None-Match` on `POST /delivery/graphql` returns 304. The same header rule applies to these GET routes.

Middleware still adds `X-Request-ID`, `Server-Timing`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, and `X-Frame-Options: DENY` on success, 304, and errors.

A draft save, a schedule capture, and a schedule failure do not change `published_data`, `published_slug`, `published_title`, `published_at`, or `published_revision`. `entry_dict` for delivery reads those columns and forces the schedule and draft-channel keys to null, so the ETag is stable until a publish, unpublish, or trash replaces or clears the live snapshot. Publishing a previously missing entry changes the list ETag. The old 404 was `no-store`, so it is not served as a cached miss.

## Draft, live, and scheduled

REST visibility is the delivery predicate already in `get_entry` and `entry_page`. `status` is not that predicate.

The working copy is `data`, `slug`, `title`, and `version`. The live snapshot is `published_data`, `published_slug`, `published_title`, `published_at`, and `published_revision`. The scheduled snapshot is `scheduled_data`, `scheduled_slug`, `scheduled_title`, `scheduled_revision`, and `scheduled_at`. `status` is the compatibility label: deleted, scheduled, published, or draft.

A delivery read keeps a row only when `published_slug` is not null and `status` is not `deleted`. `entry_page` applies that filter for a delivery identity and ignores a `status` argument. REST does not accept the argument at all. `get_entry` applies the same test before it returns a row.

Consequences of calling those functions unchanged:

- A draft with no live snapshot is absent. `GET /delivery/entries/{id}` is 404 `Entry not found.`
- A scheduled row that has not gone live has no `published_slug` and is absent. `publish_due` is what copies the captured snapshot into the live columns, after validation and the public-slug check, and only then does REST show it.
- A live row with a newer draft, a pending schedule, or a schedule failure still returns the live snapshot. `scheduled_data` and `schedule_error` are not read. `entry_dict` sets `scheduledAt`, `scheduledRevision`, `scheduleError`, `publishedData`, `publishedSlug`, `publishedTitle`, and `publishedSnapshot` to null, `hasUnpublishedChanges` to false, `status` to `published`, `version` to `published_revision`, `slug` to `published_slug`, and `updatedAt` to `published_at`.
- Unpublish and trash clear the live snapshot. The row leaves the list and the item route 404s. Restore from trash returns a working draft and does not publish it.
- `public_data` removes private fields at every level, including inside localized values, objects, and lists. A private field named `title` is removed from `data`, and the top-level `title` becomes the published slug. Filters, search, and `orderBy` use the same private-field rules as delivery GraphQL.
- Scalar filters and `orderBy` read the `published` rows of the field index, not the draft rows.

No delivery route accepts a mutation. A delivery token cannot publish, schedule, save, or trash.

## MOSS-031

Register the routes in `create_app` next to `POST /delivery/graphql`. Share the ETag helper with that route. Call the functions named above. Leave `/api` and `/auth` on `no-store`.

The implementation tests should cover a delivery bearer token and a rejected session token, `skip_auth` still requiring a delivery token, empty and named scopes, a draft and a scheduled-only entry staying hidden while the live snapshot is returned, a later draft edit and a failed schedule leaving the body and ETag unchanged, private nested fields and a private title, cursor bounds and `orderBy` on the published index, `total` omitted unless requested, 304 when `If-None-Match` repeats the list or entry ETag, no `ETag` on a 404, `no-store` and no `ETag` on resolved assets, and no cacheable delivery document mounted under `/api`. Those checks are input to QA. They are not the final acceptance criteria.

**Approved by CTO (Oct 29, 2026).**

## MOSS-032

List paging, filters, and `orderBy` stay on `entry_page`, so a delivery REST page matches the delivery `entries` connection for the same arguments. `locale` is the list and item parameter that matches a GraphQL field `locale` argument. Parity tests call both protocols.
