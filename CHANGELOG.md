# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Added the [REST delivery design](docs/rest-delivery-design.md) for review. It records delivery paths, authentication, errors, pagination, ETag caching, and the draft, live, and scheduled rule from the current API. Delivery GraphQL refusals stay HTTP 200 error payloads; the same error codes map to HTTP status codes for editorial-only fields. Those notes do not change application code. ([#15](https://github.com/nirtuttnauer/MossCMS/pull/15), `49d98a062c8d50ddd95a41479cd48b96e801ac66`, `6b0495772ea7b84f70b9a7ebc83a8edf619a6151`)
- Added cacheable GET and HEAD delivery reads under `/delivery` for types, entries, resolved assets, redirects, and reserved paths. The routes call the existing delivery helpers, share the delivery GraphQL ETag, reject a session cookie, and reject an oversized raw filters value before that value is parsed. The delivery design document is marked approved. ([#21](https://github.com/nirtuttnauer/MossCMS/pull/21), `20cedbe307318e7dbabf0ee87e68f02a4228b16f`)
- Added Dependabot coverage for the uv, npm, GitHub Actions, and Docker manifests, checked against the vendored Dependabot schema. Updates are monthly, one group per ecosystem, with an open pull request limit of 3. ([#23](https://github.com/nirtuttnauer/MossCMS/pull/23), `8ff0aca946f8a5570b3687b815c6f71176879b3a`, `5d6aff6a99024d23894078e58ff110332c2bf337`)

### Changed

- API tests register `postgres` and `compose` markers. The SQLite required run deselects the committed PostgreSQL test ids with `-m "not postgres"`, and a runtime skip fails the run. The checks workflow uses that selection for the SQLite job and sets the PostgreSQL required run. ([#16](https://github.com/nirtuttnauer/MossCMS/pull/16), `3f94ac3b232af62a7831181d1a17b622deddc758`, `5a3fcdcb6e4465f9bdcb7286b70427bb4446635a`)
- Compose builds `mosscms:local` from this checkout by default (`pull_policy: build`) instead of pulling `nirtuttnauer/mosscms:latest`. A published image is optional and requires both `MOSS_IMAGE` and `MOSS_PULL_POLICY=missing`. ([#19](https://github.com/nirtuttnauer/MossCMS/pull/19), `1b26f0fb07617e5d55303df2d25441281347f0d5`)
- The project status and task list now cite the 29 October 2026 local suite record in place of the 8 October verification counts. ([#18](https://github.com/nirtuttnauer/MossCMS/pull/18), `b9c336d397b37c9075bad0765fb375c0c513faaa`)

### Security

- Raised the API Pillow requirement from `pillow>=11.3,<13` (resolved 12.3.0) to `pillow>=13`, which resolves to 13.0.0 and includes the fixes from that release. Image upload and thumbnail code does not use the APIs Pillow 13 removed. ([#10](https://github.com/nirtuttnauer/MossCMS/pull/10), `b306d3f0e609347735880be2a3d487b1ac1500a2`)
- Updated the locked API tree to clear the remaining advisories without changing declared caps: authlib 1.8.0 to 1.9.1, certifi 2026.7.22 to 2026.10.23, and opentelemetry-api 1.45.0 to 1.45.1. The SDK pin moves opentelemetry-sdk to 1.45.1 and opentelemetry-semantic-conventions to 0.66b1. ([#14](https://github.com/nirtuttnauer/MossCMS/pull/14), `c95824b2e5d60179c4e9ca963d71606cf8247e4c`)
- Pinned GitHub Actions in the checks and docker workflows to full commit SHAs, with a version comment on every pin. The local reusable workflow path is unchanged. ([#11](https://github.com/nirtuttnauer/MossCMS/pull/11), `8f4c76e6cc1ab8dcb9db0d24e7cee664539c3e80`)
- Updated the admin lockfile from vitest and `@vitest/mocker` 4.1.11 to 4.1.12, clearing GHSA-qxg6-89mg-rqv8 and GHSA-xp26-3454-mjgp. The example site and CI lockfiles already audited clean, and no audit override or exception was added. ([#12](https://github.com/nirtuttnauer/MossCMS/pull/12), `e2b99966867b528f84d253a096d13df903f276c3`)

[Unreleased]: https://github.com/nirtuttnauer/MossCMS/compare/3a87c73c8e925973608e373863813163b41f04a9...HEAD
