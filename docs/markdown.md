# Markdown authoring

Rich-text fields remain GraphQL strings. Existing plain text is retained; no
conversion runs on save. The visual editor covers headings, emphasis, lists,
links, line breaks, fenced code, and asset images. Source mode is one action away.
A string the visual editor cannot represent, including raw HTML, quotes, and
directives, stays byte-for-byte until it is edited as source. Both localized and
non-localized fields use the same string.

Use `![Meaningful alt text](asset:ASSET_ID)` for uploaded images. Only the asset ID
is stored; authorized reads resolve a fresh download URL. Missing assets show an
unavailable-image label. Non-image assets cannot render as images. Standard HTTP(S)
image URLs and HTTP(S)/mailto links are accepted. Raw HTML and executable URL
schemes are disabled. Opening visual mode never publishes content.
