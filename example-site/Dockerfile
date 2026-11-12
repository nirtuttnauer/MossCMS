FROM node:26-alpine@sha256:c6ad9e9c1d80f6eb607c26b4b0a132ff7a2344fad1c78ea3baa2a7d4c8de6d94 AS build
WORKDIR /site
COPY shared/ /shared/
COPY example-site/package.json example-site/package-lock.json ./
RUN npm ci
COPY example-site/tsconfig.json example-site/vite.config.ts example-site/index.html ./
COPY example-site/src ./src
COPY example-site/server ./server
RUN npm run build

FROM node:26-alpine@sha256:c6ad9e9c1d80f6eb607c26b4b0a132ff7a2344fad1c78ea3baa2a7d4c8de6d94 AS runtime
WORKDIR /site
COPY shared/ /shared/
COPY --from=build /site/dist ./dist
COPY example-site/server ./server
ENV NODE_ENV=production PORT=5174
USER node
EXPOSE 5174
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s CMD node -e "fetch('http://localhost:5174/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "server/index.mjs"]
