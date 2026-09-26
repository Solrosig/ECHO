# Build the website inside the image, so it never depends on a prebuilt dist/client.
FROM node:24.19.0-bookworm-slim AS build
WORKDIR /app
RUN npm install --global pnpm@10.32.1
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

FROM node:24.19.0-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production HOST=0.0.0.0 PORT=8787 ECHO_DATA_DIR=/data
COPY --chown=node:node server ./server
COPY --chown=node:node scripts ./scripts
COPY --chown=node:node drizzle ./drizzle
COPY --chown=node:node public ./public
COPY --chown=node:node --from=build /app/dist/client ./dist/client
# All root modules in the import closure of server/start.mjs.
COPY --chown=node:node audio-outbox.js calibration-profiles.js engine-catalog.js frontend-visibility.js interactive-sync.js message-rating.js participant.js study-session.js study-sync.js voice-controls.js package.json ./
RUN mkdir -p /data && chown node:node /data
USER node
EXPOSE 8787
CMD ["node", "server/start.mjs"]
