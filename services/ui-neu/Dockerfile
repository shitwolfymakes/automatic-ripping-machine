# Docs stage: renders the repo's markdown (site/) into the JSON bundle the
# /help route reads from /docs-data/, so in-app help matches this image's
# version. Copies the whole context, not just the docs: link validation
# checks that linked repo files (services/..., devtools/..., LICENSE) exist.
FROM node:26-slim AS docs
WORKDIR /repo/site
COPY site/package.json site/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . /repo/
ARG ARM_COMMIT=unknown
RUN ARM_COMMIT=$ARM_COMMIT npm run build:app

# Stage 1 — build the SvelteKit static bundle.
FROM node:26-slim AS build
WORKDIR /app/frontend
COPY services/ui-neu/frontend/package.json services/ui-neu/frontend/package-lock.json* ./
RUN npm ci
COPY services/ui-neu/frontend/ ./
# api.gen.ts is committed; build consumes it directly (codegen needs the v3
# repo + snapshot, unavailable in the isolated build context).
RUN npm run build

# Stage 2 — nginx serving the static bundle + reverse-proxying to arm-backend.
FROM nginx:1.27-alpine
RUN apk add --no-cache ca-certificates
COPY --from=build /app/frontend/build /usr/share/nginx/html
COPY --from=docs /repo/site/build/app /usr/share/nginx/html/docs-data
COPY services/ui-neu/nginx.conf /etc/nginx/conf.d/default.conf
COPY services/ui-neu/docker-entrypoint.sh /docker-entrypoint-arm.sh
RUN chmod +x /docker-entrypoint-arm.sh
EXPOSE 443
ENTRYPOINT ["/docker-entrypoint-arm.sh"]
CMD ["nginx", "-g", "daemon off;"]
