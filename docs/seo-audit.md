# Record SEO audit

Open **SEO audit** in the workspace navigation. Live is the default; Drafts checks the saved working values, including drafts belonging to live or scheduled entries. Draft findings never replace live findings. Captured schedules and trashed records are excluded.

The report is advisory and does not edit records, block publishing, or contact external services. A clean report means no findings in the evaluated record checks. It does not establish website SEO compliance or search rankings.

## Coverage and mappings

`sitePage`, `sitePost`, and `siteProject` are pages. Their public `title` and `description` fields are audited using the bundled website's profile fallbacks. A home page (`kind: home`) uses the selected profile's `name` as its effective title. Missing page descriptions use the profile's `headline`, then `A personal website.`; missing effective titles use `Personal website`. The selected profile is the `profile` slug, or the most recently updated draft/published profile within the selected snapshot. Missing homepage profile names are reported on that profile; absent profiles are reported on the homepage.

`siteProfile` and `siteSlide` are supporting content: inspect their public Markdown, images, assets, and references without requiring page metadata.

Custom types use the first recognized public text/rich-text field from:

| Value | Precedence |
| --- | --- |
| Title | `seo.title`, `seoTitle`, `title` |
| Description | `seo.description`, `metaDescription`, `description`, `excerpt` |

Precedence is based on schema presence, not whether the value is filled. A missing title or description mapping marks the type and its records **Needs mapping**. Known fields are still checked. Review these types in Content types; the audit does not infer arbitrary field names or your custom frontend's rendering rules.

The report exposes detected mappings, page/supporting/unknown record counts, and (in Live) the count excluded for having no live snapshot. Counts cover the whole workspace; type and severity filters apply to findings only. Missing locale values are checked for configured workspace locales, alongside translations present in records. Nonlocalized content uses the default locale. Private fields and private object/list descendants are excluded.

## Rules

| Rule | Severity | Meaning |
| --- | --- | --- |
| Missing title/description | Critical without an effective value; warning with a website fallback | Supply unique, meaningful metadata or review the fallback. |
| Duplicate effective title/description | Warning | Values match after Unicode normalization, case folding, and whitespace normalization within the same snapshot and locale. |
| Empty article body | Warning | A public `body` field is empty on a blog post or a detected custom page. Listing pages/projects are not required to have a body. |
| Extra Markdown H1 | Warning | Website page Markdown adds H1s to the heading rendered by the frontend; custom content contains more than one H1. |
| Skipped heading level | Informational | Markdown jumps down more than one heading level; website pages begin with the frontend's H1. |
| Missing image description | Warning | Markdown images or image objects with a public `alt` field have empty alt text. Decorative images can intentionally remain empty. |
| Image mapping unknown | Informational | An image object has no recognized public `alt` field. Check the frontend's image description mapping. |
| Unavailable asset | Critical | A schema or Markdown asset reference is absent from this workspace; Markdown images also require a supported JPEG/PNG/WebP asset. |
| Unavailable record reference | Critical | Target record is absent/trashed; in Live, the target must have a live snapshot. |
| Long title/description | Informational | Review tips at over 60/160 characters, respectively. These are heuristics, not search-engine limits. The website's domain suffix is not counted. |

Markdown checks parse CommonMark, including reference-style images and setext headings. Fenced/inline code and raw HTML are not treated as images or headings, matching the frontend's disabled HTML rendering. Empty image descriptions require editorial judgment; do not add meaningless text to decorative images.

Website HTML, canonical tags, robots, sitemaps, performance, external link responses, indexing, and captured schedules are explicitly **Not checked**. No crawler, rank tracker, AI generation, report history, or automatic fixes are included.

## Fixing findings

Use a finding's editor link to open its draft and focus the affected field, including nested/localized fields. A live finding shows a reminder that draft edits must be published to update the live snapshot. Missing mappings link to Content types.

The editor panel checks the saved draft and labels its revision. Results are stale while edits are unsaved, and refresh after saving. Readers can inspect findings without write controls. Use Rerun/Recheck to pick up changes to referenced records or other pages.

## Editorial GraphQL

Both queries are read-only, scoped to the selected workspace, and available to readers, editors, and administrators. Delivery tokens cannot access them.

```graphql
query {
  seoAudit(snapshot: "live", first: 20, typeKey: "sitePost", severity: "warning") {
    recordCount pageCount supportingCount needsMappingCount noLiveCount
    criticalCount warningCount infoCount
    mappings { typeKey kind titlePath descriptionPath }
    findings {
      code severity entryId entryTitle typeKey snapshot revision locale
      fieldPath explanation guidance
    }
    total endCursor hasNextPage notChecked generatedAt
  }
  seoEntryAudit(id: "ENTRY_ID", snapshot: "draft", first: 20) {
    revision findings { code severity fieldPath explanation guidance }
    total endCursor hasNextPage
  }
}
```

`snapshot` accepts `draft` or `live`; workspace audits default to `live`, entry audits to `draft`. `first` is 1–100. Pass `endCursor` as `after` for the next page. Entry audits still compare metadata with all workspace records. An entry without a live snapshot returns zero inspected records and a null revision in Live; missing/trashed/cross-workspace IDs are rejected.

Findings are calculated for the complete workspace before filtering and pagination, including duplicate checks beyond the first 100 records. Assets and record references use batched workspace lookups. Reports are computed on demand with no stored state or migration. Large workspaces increase scan time. Cursors are scoped to the selected query and findings; changes that invalidate them return `CONFLICT` with instructions to rerun.
