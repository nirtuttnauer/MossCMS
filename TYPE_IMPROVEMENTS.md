# Content-type improvements — delivered scope and follow-ups

Updated 8 October 2026 after MC-07 and MC-28–MC-32. The approved P3 tasks are implemented; the original broader idea backlog also contained items outside their acceptance scope. Server validation, explicit migration review and nested constraints remain authoritative.

| Original idea | Delivered | Feature branch |
| --- | --- | --- |
| 1. Live entry-form preview | Interactive temporary values, reset on shape changes; no content writes | `feature/mc-28-schema-previews` |
| 2. Delivery shape | Matches generated nullable content fields, locale arguments, lists/objects, enum-as-string, reference/asset nodes and private exclusions | `feature/mc-28-schema-previews` |
| 3. Migration help | Before/after diff; explicit default/drop/rename suggestions, editable JSON; no automatic application | `feature/mc-29-migration-suggestions` |
| 4. Unsaved protection | Close/navigation/refresh guards for schema and entry edits | `feature/mc-07-unsaved-edit-protection` |
| 6. Enum editing | Inline choices with identifier and duplicate validation | `feature/mc-30-enum-reference-editing` |
| 7. Reference confidence | Workspace target validation, self-reference, counts and empty-target warning; referenced types protected from deletion | `feature/mc-30-enum-reference-editing` |
| 8. Title hint | Explains title-derived slug behavior without reserving the field name | `feature/mc-30-enum-reference-editing` |
| 9. Private summary | Recursive hidden-field count and public delivery shape | `feature/mc-28-schema-previews` |
| 10–11. Large schemas | Accessible up/down reordering, collapsible field cards and nested outline jump controls | `feature/mc-31-schema-outline-history` |
| 12. Version compare | Read-only current-versus-history diff | `feature/mc-31-schema-outline-history` |
| 13. Templates | Editable Article, Product, Person and Event starters | `feature/mc-32-type-templates` |
| 14. Duplication | Copy a whole type under a new unique key; deep-copy a field in its current list with a new unique name | `feature/mc-32-type-templates` |

Follow-up ideas outside MC-01–MC-34 remain open:

- Type palette (original item 5).
- Grey-out delivery-view toggle beyond the delivered count/shape (item 9).
- Drag handles beyond accessible button reordering (item 10).
- Moving fields across groups/promoting nested fields (item 11).
- Landing template (item 13).
- Cross-type field clipboard/copy-paste (item 14).
- Workspace default locales and per-type icons (items 15–16).

[Execution ledger](docs/planning/IMPLEMENTATION.md), [editor workflows](docs/editor-workflows.md) and [release evidence](docs/release-acceptance-2026-10-08.md) provide the approved scope and validation limits. Aftur's unfinished status workflow is distinct from the MCP execution attempts/artifacts.
