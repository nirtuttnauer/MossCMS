FROM node:25-alpine@sha256:bdf2cca6fe3dabd014ea60163eca3f0f7015fbd5c7ee1b0e9ccb4ced6eb02ef4 AS build
WORKDIR /site
COPY shared/ /shared/
COPY example-site/package.json example-site/package-lock.json ./
RUN npm ci
COPY example-site/tsconfig.json example-site/vite.config.ts example-site/index.html ./
COPY example-site/src ./src
COPY example-site/server ./server
RUN npm run build

FROM node:25-alpine@sha256:bdf2cca6fe3dabd014ea60163eca3f0f7015fbd5c7ee1b0e9ccb4ced6eb02ef4 AS runtime
WORKDIR /site
COPY shared/ /shared/
COPY --from=build /site/dist ./dist
COPY example-site/server ./server
ENV NODE_ENV=production PORT=5174
USER node
EXPOSE 5174
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s CMD node -e "fetch('http://localhost:5174/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "server/index.mjs"]
