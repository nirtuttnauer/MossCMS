# MossCMS competitive roadmap

Historical planning and implementation notes from 12–14 October 2026. Proposed work and intermediate states below remain dated records; use the current workflow guides and merged code for present support.

Prepared 12 October 2026. Implementation began at the owner's request on 12 October; the [implementation record](COMPETITIVE-IMPLEMENTATION-2026-10-12.md) identifies verified slices and remaining acceptance work. The scope and priorities below remain the roadmap. Work IDs are local roadmap identifiers.

Make MossCMS the strongest choice for self-hosted content teams: easy enough for editors, dependable enough for production, and affordable as both team size and content volume grow. Prioritize agencies and small to medium editorial teams delivering websites through any frontend. This is the initial audience assumption; validate it with the pilot described below.

The first competitive advantage should be a complete, dependable publishing workflow with measured operating costs. Keep the core MIT licensed and include planned permissions, approvals, releases, and integration features without per-seat or total-entry license charges. Strapi Community, Payload, and WordPress also offer free cores, so cost alone will not establish leadership. Editing quality, migration freedom, and production evidence must make the difference.

## Starting point

Build on the existing [publication contract](../publication-contract.md), [editor workflows](../editor-workflows.md), [webhooks](../webhooks.md), and [deployment and recovery tools](../deployment-recovery.md). Draft/live/scheduled snapshots, revisions, localized fields, workspace isolation, scoped delivery, media variants, and saved website previews already exist.

The [initial implementation ledger](IMPLEMENTATION.md) and [11 October backlog](IMPROVEMENTS-2026-10-11.md) record delivered work. The [12 October onboarding audit](../onboarding-audit-2026-10-12/README.md#implemented-fixes) records fixes implemented in the working tree and their review state. Complete the existing review and integration process before releasing new competitive features; do not recreate those tickets or treat historical audit observations as current defects.

Current limits include fixed roles, Markdown authoring, no approval stages or grouped releases, no REST content API, and no general extension interface. The [README comparison](../../README.md#cms-comparison) records prices and quotas separately from capabilities. Request bounds protect the server and remain useful; they are distinct from total-document license caps.

## Competitive priorities

| Reference | Capability to learn from | MossCMS priority |
| --- | --- | --- |
| [Strapi review workflows](https://docs.strapi.io/cms/features/review-workflows) and [Releases](https://docs.strapi.io/cms/features/releases) | Review stages and coordinated publication | Bring safe approval and release workflows into the free core |
| [Directus access control](https://directus.com/docs/guides/auth/access-control) and [Flows](https://directus.com/docs/guides/flows) | Configurable permissions and editorial automation | Start with understandable content permissions and a few useful automation recipes |
| [Payload APIs and configuration](https://payloadcms.com/docs/getting-started/what-is-payload) | Generated APIs and developer integration | Make connecting a frontend and extending MossCMS straightforward |
| [Sanity Studio](https://www.sanity.io/studio) and [quota rules](https://www.sanity.io/docs/platform-management/plans-and-payments#document-quota) | Visual editing and collaboration; paid document limits | Improve authoring and preview while proving larger content workloads and predictable costs |
| [WordPress Site Editor](https://wordpress.org/documentation/article/site-editor/) | Accessible visual website editing | Add comfortable visual authoring and in-context preview before considering a full site builder |

Priority reflects expected user impact, switching friction, competitive value, implementation risk, and dependencies. These judgments are product hypotheses rather than measured demand scores. P0 establishes trust; P1 makes the product easier to adopt and use; P2 expands proven workflows. Effort is relative: S is a contained change, M crosses several components, L needs a substantial contract or migration. No calendar delivery dates are implied.

## Delivery order

| Order | Work ID | Priority | Deliverable | Effort | Dependencies |
| --- | --- | --- | --- | --- | --- |
| 1 | CMP-01 | P0 | Reproducible capacity, operating cost, and recovery evidence | M | Existing release review |
| 2 | CMP-02 | P1 | Portable content export and safe import | L | Existing release review |
| 3 | CMP-03 | P1 | Typed frontend integration and a read-only REST delivery API | M | Existing release review |
| 4 | CMP-04 | P1 | Comfortable visual rich-text authoring | L | Existing release review |
| 5 | CMP-05 | P1 | Website preview beside the editor with field navigation | M | CMP-03, CMP-04 |
| 6 | CMP-06 | P1 | Configurable content permissions | L | Existing release review |
| 7 | CMP-07 | P1 | Revision-bound review and approval | L | CMP-06 |
| 8 | CMP-08 | P1 | Coordinated immediate and scheduled releases | L | CMP-06, CMP-07 |
| 9 | CMP-09 | P2 | Comments, assignments, and editing presence | M | CMP-06, CMP-07 |
| 10 | CMP-10 | P2 | Documented extensions and editorial automation recipes | M | CMP-03, CMP-06, CMP-07 |
| 11 | CMP-11 | P2 | Translation and media workflows for larger libraries | M | CMP-04, CMP-06 |
| 12 | CMP-12 | P2 | Measured query, cache, and worker scaling improvements | L | CMP-01; repeat measurements after CMP-06–CMP-08 |

Order is the recommended queue, not a requirement to finish unrelated work serially. Dependencies are the hard sequencing constraints. Staff one major feature at a time unless capacity exists for independent work. CMP-01 can expose a critical capacity defect; fixing such a defect moves the relevant CMP-12 work ahead of feature expansion.

## Work scopes and acceptance

### Capacity and operating cost evidence

**CMP-01.** Prove what a low-cost deployment can handle before promoting the absence of document caps. Extend existing recovery evidence with a repeatable benchmark and a complete cost worksheet.

- Create deterministic PostgreSQL fixtures at 1k, 10k, 50k, and 100k entries with multiple workspaces, localized fields, references, assets, and independent draft/live/scheduled snapshots. Record the exact mix and revision retention. No production content is used.
- Run a 30-minute workload with 20 concurrent delivery clients and 3 editorial writers. Report throughput, p50/p95/p99 latency, failures, database size, peak memory, CPU, and reference/query complexity. Test cache misses and hits separately and include generated GraphQL queries, list/search/filter reads, and draft saves. Pin source revision, image, seed, software versions, and hardware.
- Publish cost assumptions for compute, database, media, bandwidth, backups, and operator time. Use a proposed 4-vCPU/8-GiB reference deployment and keep frontend costs separate. Pricing inputs must be dated and sourced; provide a formula readers can adjust.
- Rehearse backup, restore, upgrade, and worker restart on the 100k-entry fixture. Verify identifiers, live content, private-field exclusion, revision recovery, media, and captured schedules. Report measured recovery time and backup age; optimize only demonstrated bottlenecks.

**Success gate:** publish actual results and supported workload guidance. Performance targets below are provisional and cannot become README claims until measured. A benchmark failure is evidence to fix, not a result to omit.

### Portable content import and export

**CMP-02.** Let teams adopt or leave MossCMS without rebuilding content by hand. Start with a documented, versioned MossCMS interchange format and one Sanity adapter, reflecting the owner's concern about document limits. Add other adapters after pilot demand.

- Export workspace schemas, locales, entries, durable asset mappings, references, and explicitly selected history. Allow admins to include private content deliberately. Exclude sessions, password hashes, OAuth credentials, webhook secrets, delivery tokens, and preview grants. Operational database backups remain a separate tool.
- Provide a dry run that reports unsupported fields, Portable Text conversions, slug conflicts, missing references/assets, and estimated record counts. Sanity input uses an authorized export; retain source IDs in the mapping. Never silently flatten or discard unsupported blocks or field types.
- Import into a selected empty workspace by default. Stage media and mappings, validate before activation, and expose resumable progress without duplicate entries/assets. A cancellation or failed batch must leave recoverable state. Published source content imports as drafts unless the operator explicitly selects a publication step.
- A round trip of a 1k-entry fixture preserves supported field values, locales, references, slugs, asset bytes, and selected revision metadata. Test interruption/retry and inaccessible references. Produce a report of every unsupported or intentionally transformed value.

### Frontend integration and REST delivery

**CMP-03.** Reduce integration work for developers while preserving a single content and permission contract.

- Provide a small TypeScript delivery client or generated client recipe with typed query examples, cursor iteration, locale selection, structured errors, request IDs, and signed-media handling. Type regeneration explicitly follows schema changes.
- Add read-only REST list and single-entry delivery endpoints with an OpenAPI contract. Share published snapshot selection, workspace/token scopes, public field projection, cursor bounds, and cache behavior with GraphQL. Neither protocol can read drafts or mutate content using a delivery token.
- Ship copyable server examples and one supported Next.js starter alongside the existing React/Node example. Keep secrets on the server. Show publication invalidation and preview integration without automatic publication or insecure browser tokens.
- Three developers unfamiliar with MossCMS must independently connect a starter, read localized published content, paginate, and handle an error. Target completion within 30 minutes after the CMS is ready; retain observed results. Protocol parity tests cover nested private fields, scoped types, missing assets, and workspace isolation.

### Visual rich text authoring

**CMP-04.** Make common writing tasks comfortable for editors without requiring Markdown knowledge. Preserve existing `richText` strings and source editing.

- Prototype a visual editor for the Markdown subset already supported by MossCMS: headings, lists, links, emphasis, code, and durable image references. Preserve content the visual editor cannot represent through an explicit source mode; do not perform lossy conversion automatically. Choose a structured rich-text field only if the prototype proves Markdown cannot meet the pilot needs, with its own migration contract.
- Reuse autosave, revision recovery, validation, and asset selection. Formatting, pasted content, and image insertion must work with keyboard input, mobile layouts, RTL text, and an actual screen reader.
- Round-trip a representative content corpus through both modes without losing supported formatting, asset IDs, or unsupported source text. Existing frontends, stored revisions, and schedules continue to render correctly. Apply the same safe rendering policy across editor, preview, and website.

**Success gate:** at least 4 of 5 pilot editors complete a defined writing/formatting/image task without help, with no data loss. Record whether completion improves over the current editor.

### Preview beside the editor

**CMP-05.** Let editors see their actual website and navigate back to the field that controls it.

- Add a side-by-side preview using the existing expiring saved-revision grant and trusted website origin. Clearly show unsaved changes, the revision being previewed, and refresh state. Start with explicit saved preview refresh rather than introducing streaming writes.
- Support an optional frontend mapping from rendered elements to an entry ID and field path. Clicking an element focuses the allowed field in the editor; absent mappings fall back to entry navigation. Treat messages and identifiers as untrusted and verify the origin and workspace.
- Preview never exposes private fields, enters public caches, or changes public content. Expiry/revocation ends access. Verify desktop, mobile fallback, keyboard navigation, and the example site plus the Next.js starter.

### Configurable content permissions

**CMP-06.** Separate writing, publishing, and administration, then allow teams to restrict selected content types and fields.

- Replace role rank assumptions with shared explicit capabilities. Preserve existing role behavior through migration; administrators opt into new author/publisher presets and custom policies. Keep a recoverable administrator and explain effective permissions in the UI.
- Define workspace and content-type actions for read, create, edit, publish, schedule, review, media, schema, and team administration. Add nested field read/write rules with a documented composition contract. Protected writes must preserve restricted stored values rather than erase them from partial forms.
- Enforce policies in GraphQL, REST, preview issuance, imports, revisions, search/filter/sort/count surfaces, and worker actions. Admin UI hiding alone is insufficient. Test attempts to infer restricted values through filters, references, totals, errors, and historical versions. Public/private delivery rules remain a separate lower bound on exposure.
- Test permission changes during editing and scheduled work, removed users, cross-workspace access, and schema field renames. An admin can explain and test a user's effective access before saving a policy.

### Review and approval

**CMP-07.** Add a small workflow: Draft → In review → Approved → Published, with return-for-changes and an assigned reviewer. Approval and publication are distinct capabilities.

- Bind approval to an immutable content revision, slug, and schema version. Any material edit or migration invalidates approval. Configure approval requirements per type; existing workspaces keep their current publishing behavior until enabled.
- An author who lacks publishing permission can submit for review but cannot bypass approval through APIs, imports, restores, scheduling, or release groups. When required, the reviewer must be a different person from the author. Show the exact diff being approved and record decisions in audit history.
- Publication and scheduling require a valid approval for the captured revision. Recheck relevant policies, reviewer/publisher eligibility, and schema validity when scheduled work executes; failure preserves live content and gives a clear recovery path.

### Coordinated releases

**CMP-08.** Publish a set of related entries together for a launch or campaign, using captured approved revisions.

- Provide release creation, entry selection, diff/validation, an immediate or scheduled action, and explicit replacement/cancellation. Start with publish/unpublish actions within one workspace; later draft edits do not change captured release contents.
- Validate slugs, policies, approvals, and references across the whole release. Either commit every selected publication action or none; a failed entry preserves all previous live snapshots. Define conflicts between individual schedules and release membership, and bound release size using measured transaction cost.
- Use durable idempotent execution and existing transactional events. Test worker concurrency, crash/restart, approval revocation, conflicting slugs, and references between entries published in the same release. Expose a release completion event so integrated frontends can refresh after the complete commit; describe cache propagation as eventual unless a frontend proves atomic refresh.

### Editorial collaboration

**CMP-09.** Improve coordination before taking on simultaneous text merging.

- Add comments and assignments linked to entry/revision/field, a review inbox, and in-app notifications. Permission checks apply on every read/write, including removed members and restricted fields. Comments on older revisions retain their context.
- Add advisory editing presence and retain optimistic conflict detection. Stale sessions expire; presence never claims a lock or protects writes by itself. Two-editor tests must preserve both sets of unsaved work and expose a usable diff/recovery path.
- Measure review turnaround and conflict frequency with pilot teams before deciding whether simultaneous editing is worth its operational complexity.

### Extensions and workflow recipes

**CMP-10.** Make common integrations possible with a small documented interface.

- Start with versioned events, a server extension contract, and three recipes: review notification, publish-triggered frontend rebuild, and media processing. Reuse signed webhooks and outbox retries wherever possible; authoring and publication remain successful if an external service is unavailable.
- Specify compatibility, permissions, secret handling, retry/idempotency, and what runs inside or after transactions. Server extensions are trusted operator-installed code, not untrusted uploads or sandboxed programs.
- Test timeout, duplicate event, failed service, extension removal, and upgrade behavior. Add custom admin field components only after a concrete integration needs them. A general drag-and-drop workflow designer follows demonstrated recipe demand.

### Translation and media libraries

**CMP-11.** Extend existing locales, the paginated asset picker, image variants, and focal points rather than recreate them.

- Add missing-translation indicators and side-by-side locale editing, with an explicit fallback policy and a diff against the source locale. Changes in one locale must preserve others. Translation publishing uses the same review rules; define whether approval is per entry or per locale before changing that contract.
- Add asset organization, searchable metadata/alt text, and usage lookup across working/live/scheduled/history references. Deletion must explain dependencies; replacement cannot silently change a captured or live revision. Offer reversible organization changes before bulk deletion features.
- Verify a five-locale fixture with RTL content and an asset library beyond the first result page. Pilot editors must find missing translations and identify assets in use without manual API queries.

### Query and deployment scaling

**CMP-12.** Improve only the bottlenecks demonstrated by CMP-01 or real pilot workloads. The owner's follow-up selected automatic scalar ordering and OpenTelemetry first; [the performance/scaling plan](PERFORMANCE-SCALING-2026-10-12.md) records implementation and measured gates for replicas and sharding.

- Inspect actual PostgreSQL query plans for search, scalar filters, totals, and generated schema construction. Prefer targeted indexes, bounded query changes, and avoiding unnecessary totals before adding a search service or queue broker. Document revision/media retention controls and safe configurable request/upload bounds.
- Validate multiple app/worker processes with PostgreSQL and shared media. Prove schedules and outbox work are claimed safely across restart and deployment; run isolation checks alongside the load test.
- If read traffic needs caching, design keys around workspace, token scope, schema version, publication revision, and asset-link expiry. Never put drafts or scoped responses into an unpartitioned public cache. Provide a frontend/CDN adapter and invalidation contract before a managed CDN service.
- Repeat the original fixture and load test on the same hardware. Publish before/after results and monthly cost at the measured load; retain request limits that protect availability.

## Milestones and release gates

| Milestone | Work | Completion gate |
| --- | --- | --- |
| Adoption and trust | Existing review, CMP-01–CMP-03 | Current fixes accepted/integrated, public scale/cost evidence, verified import round trip, and independent frontend setup |
| Editing and team publishing | CMP-04–CMP-08 | Pilot editors succeed; permission checks cover every entry point; stale approvals and failed releases preserve live content |
| Everyday team operations | CMP-09–CMP-11 | Pilot teams complete review, notification, translation, and media tasks with evidence of less manual work |
| Larger deployments | CMP-12 | A demonstrated bottleneck is resolved with repeated benchmarks and recovery checks |

Each feature release includes meaningful API/UI/integration coverage, migration and rollback guidance when stored data changes, a disposable PostgreSQL recovery rehearsal where relevant, and keyboard/mobile/screen-reader acceptance for changed editor flows. Update the README comparison only after the feature and its evidence pass their gates. External-provider tests and pilot observations must be identified as such, not inferred from unit tests.

## Measures of leadership

These are proposed acceptance targets, not current results or service guarantees. Record the baseline first and adjust the performance targets if the reference workload demonstrates they are inappropriate.

| Outcome | Initial target | Evidence |
| --- | --- | --- |
| First useful content | 4 of 5 new editors independently publish and verify delivery within 10 minutes after a ready instance and sign-in | Timed pilot tasks; retain failures and assistance given |
| Frontend integration | 3 of 3 developers connect the starter within 30 minutes | Fresh setup recordings and successful delivery/preview requests |
| Content scale | Complete 100k-entry import, ordinary editing, publication, and recovery without a software total-entry cap | CMP-01 fixture and CMP-02 round trip; report actual throughput |
| API responsiveness | At 50k entries on the reference deployment, proposed p95 below 300 ms for a 20-entry delivery list and below 750 ms for an ordinary draft save under the specified load | Separate cold/warm runs, error rate, resource use, query shape |
| Publication reliability | No lost live snapshots or duplicate committed publication effects in retry/restart/conflict scenarios | Contract tests, worker fault injection, recovery rehearsal |
| Predictable cost | Publish a complete monthly cost model for 10 editors and the 50k/100k-entry fixtures, with stated traffic and retention assumptions | Dated infrastructure inputs; seat charges, content charges, and infrastructure costs separated |
| Switching freedom | Supported content round-trips without silent loss; unsupported source fields are explicitly reported | Export/import manifests and value/asset checks |
| Editor confidence | 4 of 5 editors complete writing, preview, review, and correction tasks unaided; publish task-level results | Before/after pilot sessions and accessibility checks |

Comparative claims require matched tasks and workloads against actual competitor installations/plans. Vendor documentation establishes feature availability; it cannot establish that MossCMS is faster, cheaper to operate, or easier to use.

## Larger investments after validation

| Investment | Condition for starting | Initial boundary |
| --- | --- | --- |
| Simultaneous collaborative editing | Pilot teams repeatedly need to edit the same entry together and CMP-09 conflict/presence tools remain inadequate | One supported rich-text field format; define merge, undo, revision, approval, offline, and access-revocation semantics before implementation |
| Full visual site builder | At least three pilot teams need layout composition that schemas, the starter, and CMP-05 cannot meet | Reusable structured blocks and frontend adapters first; preserve frontend independence |
| Plugin marketplace | At least three independent integrations use CMP-10 and stable version/support rules exist | Curated examples and compatibility guidance before public uploads or distribution |
| Managed hosting and CDN | Pilots demonstrate demand and the measured service can support a sustainable operating model | Optional hosting priced by infrastructure/service needs; free self-hosting remains complete. Define backups, regions, incident response, support, and costs before promising an SLA |
| AI writing and translation | Pilot users identify a repeated job with measurable benefit | Explicit user action, editable suggestions, and operator-provided credentials; no automatic publication |

Revisit priorities after each milestone with pilot results, support issues, adoption obstacles, and measured cost/performance. Promote a later item only when that evidence outweighs the current queue. The first implementation slice is CMP-01 plus a draft interchange contract for CMP-02 and typed integration examples for CMP-03.
