# Mirrors clinic-cms/skcms, which has run this shape in production for months.
# Simplified where prospect is simpler: one site, so no ENV_FILE build arg and
# no skvar submodule; no patches/ directory.

# --- Stage 1: Base, with dependencies installed from the lockfile ---
FROM node:22-slim AS base

ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
# adapter-node sits behind nginx, which terminates TLS. Without these it builds
# redirect and canonical URLs from the internal http:// host it was reached on.
ENV PROTOCOL_HEADER=x-forwarded-proto
ENV HOST_HEADER=x-forwarded-host
RUN corepack enable && npm install -g corepack@latest
WORKDIR /app
COPY . .
# --frozen-lockfile: fail rather than silently resolve something the lockfile
# does not describe. corepack pins pnpm to package.json's packageManager field.
RUN --mount=type=cache,id=pnpm,target=/pnpm/store \
    pnpm install --frozen-lockfile

# --- Stage 2: Build ---
FROM base AS builder
RUN pnpm run build

# --- Stage 3: Production runtime ---
FROM node:22-slim AS production
ARG GIT_SHA
LABEL git.sha=$GIT_SHA
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
ENV NODE_ENV=production
ENV PROTOCOL_HEADER=x-forwarded-proto
ENV HOST_HEADER=x-forwarded-host
RUN corepack enable && npm install -g corepack@latest
WORKDIR /app
COPY --from=builder /app/package.json .
COPY --from=builder /app/pnpm-lock.yaml .
RUN --mount=type=cache,id=pnpm,target=/pnpm/store \
    pnpm install --prod --frozen-lockfile
# Contents of build/ land at /app, so the entrypoint is index.js — not
# `node build`, which is what the npm-based image used.
COPY --from=builder /app/build .

RUN addgroup --system app && adduser --system --ingroup app app
USER app

EXPOSE 3000

CMD ["node", "index.js"]
