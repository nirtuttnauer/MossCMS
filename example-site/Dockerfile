FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS build
WORKDIR /site
COPY shared/ /shared/
COPY example-site/package.json example-site/package-lock.json ./
RUN npm ci
COPY example-site/tsconfig.json example-site/vite.config.ts example-site/index.html ./
COPY example-site/src ./src
COPY example-site/server ./server
RUN npm run build

FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS runtime
WORKDIR /site
COPY shared/ /shared/
COPY --from=build /site/dist ./dist
COPY example-site/server ./server
ENV NODE_ENV=production PORT=5174
USER node
EXPOSE 5174
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s CMD node -e "fetch('http://localhost:5174/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "server/index.mjs"]
