# Stage 1: Build
FROM node:22-slim AS builder

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .
RUN npm run build

# Stage 2: Runtime
FROM node:22-slim

WORKDIR /app

COPY --from=builder /app/build ./build
COPY --from=builder /app/package.json ./
RUN npm install --omit=dev

RUN addgroup --system app && adduser --system --ingroup app app
USER app

EXPOSE 3000

ENV NODE_ENV=production
CMD ["node", "build"]
