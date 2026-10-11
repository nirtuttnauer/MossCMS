# Safari keyboard and editor checks — 11 October 2026

This records agent-operated checks in a fresh, authenticated synthetic fixture. It supplements the [editing acceptance report](../editor-acceptance-2026-10-11.md); it does not establish human usability improvement or complete TASK-45.

## Isolation and method

The separate UI used `http://[::1]:15115` and its API used `http://[::1]:18115`. Authentication was enabled. A temporary Vite proxy configuration used an object target with hostname `::1` for this fixture; this was a local isolation configuration, not a production hosting change. No credentials or delivery tokens are recorded here.

Native Safari **27.0.1, build 22625.1.29.11.28** used actual **200% Page Menu zoom**. The owner authorized coordination with the other Safari chat. Initial actions used batches followed by accessibility observations. A window switch allowed a batched sequence to reach an unrelated window; this was reported, and subsequent key actions checked the owned window UUID and fixture URL both before and after input. Later tab switches stopped input safely. The owner then paused other Safari use for the final retests. In-app browser checks are identified separately and are not claimed as a versioned standalone Chromium run.

## Verified workflows

| Check | Observed result |
| --- | --- |
| Workspace locale settings, in-app browser | Changed the synthetic workspace from `en` to default `he` with suggestions `he, en, ar`. Duplicate suggestions and a default absent from suggestions were rejected while inputs remained intact. A new Validation entry initialized Hebrew authoring. |
| Reference outside first 100, in-app browser | The fixture held 160 Person targets. Keyboard search for the oldest target, `000`, selected and saved the independently resolved reference. |
| Nested/list/group validation, in-app browser | Required nested Note, required list item 1, and the localized group after removing all translations each exposed the corresponding error and focus target. |
| List validation, Safari at 200% | Space activated Add item and Save. Save focused the required `Steps 2` input. Enter on the summary link reached that same input; entering `Second step` corrected the value. |
| Empty localized group, Safari at 200% | Removing the last `he` translation and activating Save with a pointer focused the Translations group. The initial screenshot showed only its normal gray border, revealing a missing visible focus ring. The added `.field-group:focus` rule supplied a 3px accent outline, 3px offset and 100px scroll margin. |
| Locale summary and recovery, Safari at 200% | Both Enter on the summary link and a coordinate pointer click focused Translations without changing the editor route. The final screenshot shows the group ring, error and sticky Save together. Tab from the group reached the locale selector; entering custom `he` and activating Add with Space restored the translation. |
| Comparison keyboard navigation, Safari | Right, Home and End operated the comparison mode tabs. Shift-Tab reached Close comparison; forward Tab wrapped within the dialog to Close. |
| Restore cancellation, Safari at 200% | Space on Restore v3 opened the confirmation. Tab reached Confirm, then Cancel. Space on Cancel returned focus to Restore v3. Escape closed the comparison and returned focus to its opener. This cancellation path did not execute a restore. |
| Saved-entry unsaved edit, Safari | Cleared the saved score (`0`), then Back and native Cancel retained the blank edit. Forward retained it as well. Pointer navigation to Settings followed by Cancel also retained the editor. |
| Unsaved duplicate and list context, Safari | From a list filtered by `Keyboard validation` and sorted `title_asc`, keyboard Duplicate opened a new form. Editing its title to `Keyboard unsaved copy` did not create a background record. Back/Cancel and Forward retained the new-entry hash, edited title, filter and sort. Keyboard Settings/Return followed by Escape to cancel retained the form and returned focus to Settings. Back to content/Space followed by native OK/Return discarded the copy and restored the list filter and sort. |
| Upload and Markdown insertion, in-app browser | Uploaded a synthetic 32×32 PNG. Success exposed status text and returned focus to Choose asset. Insert image remained gated by alt text. After supplying alt text, insertion returned focus to the textarea and stored an `asset:` reference whose ID starts `1bc7cfa2`. Preview displayed the image with its alt text; save/reopen retained it and comparison remained readable. |
| Saved-status recovery, Safari | At saved version 4, clearing score `0` exposed `Incomplete`; restoring `0` returned the status to `Saved`. The backend version remained 4, confirming recovery did not create a redundant write. |
| Image selection and Markdown insertion, Safari at 200% | Option-Tab traversed the image picker’s Upload control, Search and PNG result. Space selected the PNG and returned focus to Choose asset. Insert image remained disabled until alt text `Second synthetic square` was entered. Space on Insert image returned focus to the Body textarea. Its exact Markdown retained the original image and `Keyboard draft body.` while prefixing the second image. Space on Preview exposed both images with their respective alt text in the native accessibility tree; the screenshot records the rendered preview. This was selection of a library PNG, not a repeated upload through Safari’s native file chooser. |
| Reference and explicit save, Safari | Space on Choose reference opened the picker. Tab traversed Clear and Search; pasting `Keyboard person 000`, then Tab and Space on its target, selected it and returned focus to Choose reference. Keyboard Save draft succeeded and returned to the list with search and `title_asc` sorting preserved. |

Final guarded API assertions confirmed **version 5**, exactly two Markdown image references to the same 32×32 asset, the two steps, Hebrew translation, nested Note, score `0`, unchecked boolean `false`, and oldest Person reference. Native Safari reopening retained the exact Markdown and showed `Draft: Saved`. The entry remained draft with no live snapshot, publication or schedule. No `Keyboard unsaved copy` entry persisted. The earlier identical-value status recovery retained version 4 without a write.

The full web suite passed **271 tests across 28 files**, followed by TypeScript and a successful production build. Comparison and autosave regression tests cover tab keys, all restore Cancel origins, disabled tabs, and valid values restored to the acknowledged saved fingerprint. The checks do not establish preservation of the exact browser history index: canceled traversal rewrites the destination entry, and a subsequent same-route traversal can retain the form without another prompt.

## Visual evidence

- [New-entry Hebrew default at narrow width](new-entry-he-default-mobile.png)
- [Required list-item validation at narrow width](validation-list-mobile.png)
- [Localized-group validation at narrow width](validation-locale-group-mobile.png)
- [Safari list-item validation at 200%](safari-keyboard-list-200.png)
- [Safari localized-group focus ring, error and sticky Save at 200%](safari-keyboard-locale-200.png)
- [Safari restore cancellation and focus recovery at 200%](safari-keyboard-restore-cancel-200.png)
- [Safari dirty-navigation cancellation](safari-keyboard-dirty-cancel.png)
- [Safari two-image Markdown preview at 200%](safari-keyboard-image-preview-200.png)

## Limits and cleanup

- Native Safari library-image selection, insertion/preview, keyboard save and reopen are verified. A final native file-chooser upload at restored 100% also succeeded: Space on Upload, Go to Folder to the exact synthetic PNG, selection confirmation, then Return on Upload. The path field needed explicit focus/value assignment; no unrelated file was selected. Success exposed `Uploaded and selected keyboard-upload.png.` and focused Choose asset, while the entry stayed at version 5/Saved. [Native upload evidence](safari-keyboard-native-upload.png).
- The stale `Incomplete` autosave-status browser retest **passed** with no version change, as recorded above.
- Spoken VoiceOver labels, status and recovery announcements remain owner-deferred. No VoiceOver audio was captured or verified in these checks. Standalone Chromium repetition remains owner-deferred; no browser installation is claimed.
- These are agent-operated walkthroughs, not human study participants or a measured activation improvement. No production data or deployment was involved.
- Temporary tabs were closed; native zoom was restored to its observed original 100% and the previously active Audit tab was restored. Final API assertions found two 32×32 PNG assets and the unchanged version-5 draft. Both initial and final owning API/UI sessions exited, and ports 18115/15115 had no listeners. The temporary configuration and fixture files remain in `/tmp` for reproduction; no repository proxy change was made for IPv6.
