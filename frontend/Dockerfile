# Stage 1: Build
FROM node:22-slim AS builder

RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app

COPY package.json pnpm-lock.yaml ./
RUN pnpm config set onlyBuiltDependencies "esbuild" && pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

# Stage 2: Runtime
FROM node:22-slim

RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app

COPY --from=builder /app/build ./build
COPY --from=builder /app/package.json ./
COPY --from=builder /app/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile --prod

RUN addgroup --system app && adduser --system --ingroup app app
USER app

EXPOSE 3000

ENV NODE_ENV=production
CMD ["node", "build"]
