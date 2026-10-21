# Contributing to MossCMS

Bug reports, documentation improvements, and pull requests are welcome.
For substantial changes, open an issue first to discuss the approach.

Follow the setup and development instructions in [README.md](README.md).
Use Python 3.12 or newer with uv, Node.js 22 or newer, and Docker Compose
for the PostgreSQL-backed application.

Keep changes focused and run the checks listed in the README for the parts
you change. Add regression coverage for behavior changes. Describe the
problem, resulting behavior, and validation in your pull request.

## Admin UI changes

Follow [the admin design system](DESIGN.md) and reuse the existing controls in
`web/src/components/ui/`. The guide includes component examples, runtime token
names, responsive rules, and validation commands. Preserve the current palette,
typography, and draft/live distinctions during scoped refinements.

When a shared design rule intentionally changes, update `DESIGN.md` and
`.impeccable/design.json` together. The sidecar's HTML/CSS is for visual previews;
use the React components for application behavior. This system applies to the
admin in `web/`; the example website has its own design.

## Credentials and licensing

Never commit credentials, local environment files, database backups, or
user-uploaded media. Use the checked-in `.env.example` files as templates.

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE).
