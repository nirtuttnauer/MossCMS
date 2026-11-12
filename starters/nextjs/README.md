# MossCMS Next.js starter

A Next.js app that renders published MossCMS entries as live pages. Server code imports [`shared/delivery.mjs`](../../shared/delivery.mjs), [`shared/routes.mjs`](../../shared/routes.mjs), and [`shared/markdown.mjs`](../../shared/markdown.mjs) from this repository. The delivery token stays in the server environment.

Run it from a checkout of this repository, with Node.js 22 or newer and MossCMS already running.

## Configure

```sh
cp .env.example .env
```

Set `MOSS_API_URL` to the MossCMS origin and `MOSS_DELIVERY_TOKEN` to a delivery token for the workspace. Leave the token out of any `NEXT_PUBLIC_` variable. The delivery API returns published entries in the token's scope. This app does not route an entry whose status is present and is not `published`, or an entry with no publication time. Drafts therefore have no page.

## Routes and Markdown

Paths come from `pagePath` and `routePage`. A slug of `home`, or a page whose kind is `home`, is served at `/`. Example-website posts and projects keep the `blog/` and `projects/` prefixes, and a unique legacy slug redirects to that path. Historical redirects and reserved paths from the delivery API are passed through to the same helpers. Markdown bodies use the shared URL policy: raw HTML is left unrendered, and link or image URLs must be `http`, `https`, or (for links) `mailto`. An `asset:` image uses a resolved image URL from the entry when the delivery response includes one.

`/` lists published entries when none of them is the home page. Any other unknown path, including a draft slug, is not found.

## Run

```sh
npm ci
npm test
npm run dev
```

Open http://localhost:3000.

`npm run build` compiles the app without contacting MossCMS. `npm start` serves that build.

Preview grants, media galleries, and per-page metadata tags are left for later starter work.
