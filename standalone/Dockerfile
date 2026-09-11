FROM node:24.19.0-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production HOST=0.0.0.0 PORT=8787 ECHO_DATA_DIR=/data
COPY --chown=node:node server ./server
COPY --chown=node:node scripts ./scripts
COPY --chown=node:node drizzle ./drizzle
COPY --chown=node:node public ./public
COPY --chown=node:node dist/client ./dist/client
COPY --chown=node:node study-session.js model-config.js frontend-visibility.js package.json ./
RUN mkdir -p /data && chown node:node /data
USER node
EXPOSE 8787
CMD ["node", "server/start.mjs"]
