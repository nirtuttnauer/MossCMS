# Markdown authoring

Rich-text fields remain GraphQL strings. Existing plain text is retained; no
conversion runs on save. Both localized and non-localized fields support headings,
emphasis, lists, links, fenced code, quotes and images. Single line breaks remain
visible. Use the formatting buttons or type Markdown directly, then select Preview.

Use `![Meaningful alt text](asset:ASSET_ID)` for uploaded images. Only the asset ID
is stored; authorized reads resolve a fresh download URL. Missing assets show an
unavailable-image label. Non-image assets cannot render as images. Standard HTTP(S)
image URLs and HTTP(S)/mailto links are accepted. Raw HTML and executable URL
schemes are disabled. Previewing never publishes or rewrites the source string.
