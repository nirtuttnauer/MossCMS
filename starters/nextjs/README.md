# MossCMS Next.js starter

A minimal Next.js app that lists published entries from MossCMS. Server code imports [`shared/delivery.mjs`](../../shared/delivery.mjs) from this repository. The delivery token stays in the server environment.

Run it from a checkout of this repository, with Node.js 22 or newer and MossCMS already running.

## Configure

```sh
cp .env.example .env
```

Set `MOSS_API_URL` to the MossCMS origin and `MOSS_DELIVERY_TOKEN` to a delivery token for the workspace. Leave the token out of any `NEXT_PUBLIC_` variable. The delivery API returns published entries in the token's scope. Drafts are not included.

## Run

```sh
npm ci
npm run dev
```

Open http://localhost:3000.

`npm run build` compiles the app without contacting MossCMS. `npm start` serves that build.
