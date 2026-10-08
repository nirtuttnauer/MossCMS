# Content-type creation — improvement backlog

Grounded in what the schema supports: 10 field types (text, richText, number, boolean, date, enum, object, list, reference, asset), 1–40 fields per object, up to 5 nesting levels, localized maps, private fields, references, explicit migrations, and a delivery GraphQL API.

Work top to bottom. Each item is scoped to one focused change. Mark `- [x]` when done and note the commit.

## Tier 1 — high leverage (reuse existing code)

- [x] **1. Live entry-form preview.** Render the authoring form (`FieldInput`) in a right-hand pane so the schema shows what editors will actually fill in, updating live as fields change. ✅
  - Why: closes the gap between "I defined a field" and "what will editing look like".
  - How: reuse `FieldInput` from `Content.tsx`; fetch references + assets the way `EntryEditor` does; initialize values with `initialData`.

- [ ] **2. Live delivery shape.** Show the generated GraphQL type as the schema is built (`title: String!`, `category: CmsCategory`, `author: CmsEntryRef!`, localized as `(locale)`).
  - Why: ties the schema to the API explorer and reveals what a delivery client will query.
  - How: pure function mapping `Field[]` → SDL-ish text, rendered read-only under the builder.

- [ ] **3. Smart migration prefill.** Compute a before/after field diff and auto-fill the migration (`drop` for removed, `rename` for renamed, `defaults` for new required).
  - Why: migrations are mandatory for incompatible edits and are the scariest part of editing a live type.
  - How: diff top-level field names/types; seed the existing migration textarea; user can still override.

- [ ] **4. Guard on close / unsaved draft.** Warn (or autosave a draft) when the dialog closes with unsaved changes.
  - Why: currently it silently discards work.
  - How: track "dirty" vs the initial schema; `beforeunload`/close handler + optional localStorage draft.

## Tier 2 — real UX upgrades

- [ ] **5. Type palette.** A row of labeled, icon-tagged type buttons that add the right starter field in one click, instead of "Add field → Text, then switch type".

- [ ] **6. Inline enum chip editing.** Click a choice to rename it (not just add/remove); live-warn on non-identifier or duplicate values before submit.

- [ ] **7. Reference confidence.** Show entry count per target type; warn when the target has zero entries or no longer exists (upgrade the "(not in this workspace)" case to a real error).

- [ ] **8. `title` hint.** Surface that naming a field `title` enables slug-from-title generation in the entry editor (it is special, not reserved).

- [ ] **9. Private / delivery summary.** A tally ("N fields hidden from delivery") plus a "delivery view" toggle that greys out private fields.

## Tier 3 — large schemas (30+ fields, deep nesting)

- [ ] **10. Drag-to-reorder.** Replace the ↑↓ arrows with drag handles for large fields lists.

- [ ] **11. Collapsible cards + outline.** Collapse field cards; add a mini schema-tree with jump-to; support "move into group" / promote.

- [ ] **12. Version compare.** Diff the current schema against any past version from the stored schema history.

## Nice-to-have

- [ ] **13. Templates.** One-click starter field sets (Article, Product, Person, Event, Landing).

- [ ] **14. Duplicate.** Duplicate a whole type, or copy a single field across types.

- [ ] **15. Default locales.** Pre-seed localized fields with the workspace's default locales.

- [ ] **16. Per-type icon.** An icon on each type card for scannability.

## Progress log

| # | Item | Status | Notes |
| --- | --- | --- | --- |
| 1 | Live entry-form preview | ✅ done | 2-pane dialog; `FieldInput` preview with `initialData`; reset on shape change via `shapeSignature` |
| 2 | Live delivery shape | | |
| 3 | Smart migration prefill | | |
| 4 | Guard on close | | |
| 5 | Type palette | | |
| 6 | Inline enum editing | | |
| 7 | Reference confidence | | |
| 8 | `title` hint | | |
| 9 | Private/delivery summary | | |
| 10 | Drag-to-reorder | | |
| 11 | Collapsible + outline | | |
| 12 | Version compare | | |
| 13 | Templates | | |
| 14 | Duplicate | | |
| 15 | Default locales | | |
| 16 | Per-type icon | | |
