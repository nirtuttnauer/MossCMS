# Permissions

Classic workspace roles keep their current access until an administrator turns custom permissions on. Delivery tokens stay read-only and do not use these team rules. Private fields remain a delivery concern.

## Capabilities

| Capability | What it allows |
| --- | --- |
| read | View drafts, history, and the publication queue |
| create | Create entries |
| edit | Change drafts and restore a historical revision as a draft |
| publish | Publish now, unpublish, and publish a release |
| schedule | Schedule an entry or a release, and retry a captured schedule |
| review | Approve or return a submitted revision |
| media | Upload assets |
| schema | Change content types and require review |
| team | Invite people, change roles, and edit permission settings |

| Role | Capabilities | Available |
| --- | --- | --- |
| reader | read | Always |
| editor | read, create, edit, publish, schedule, review, media | Always |
| admin | every capability | Always |
| author | read, create, edit, media | After custom permissions |
| publisher | read, create, edit, publish, schedule, review, media | After custom permissions |

Checks run in GraphQL, import, preview issuance, revision restore, and the publication worker. Hiding a button is not the check. Import stays limited to administrators and creates drafts, so it cannot bypass a required approval. An author can restore a revision only as a draft.

Administrator access means both schema and team. An edit check includes authors. Publish, schedule, media, and schema are separate capabilities. Turning custom permissions off is refused while any member is an author or publisher.

## Field-rule composition

Field rules are stored on the workspace and ignored until custom permissions are on. The shape is an allow-list:

```json
{"article": {"author": {"read": ["title", "body"], "write": ["title"]}}}
```

- `*` means every field. A missing role entry also means every field.
- Paths are `title`, `meta.note`, or `sections.*.caption`.
- Rules cannot name `admin`. Administrator access is never removed.
- A writable path must also be readable.
- A save merges incoming values over the stored entry. Fields outside the write list keep their stored values, including when the form omits them or sends null.
- Editorial entry data, the published snapshot shown in the editor, and historical revision snapshots omit fields outside the read list.
- A hidden title is shown as the slug and is excluded from search, filters, and ordering.
- A filter or order on a hidden scalar field returns `Filter on a visible scalar field.` The error does not include the submitted value.
- The same redaction applies when the entry is reached through a reference, a list total, or a historical version.
