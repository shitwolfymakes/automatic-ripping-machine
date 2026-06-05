# Stage 1 — build the SPA bundle.
FROM node:22-alpine AS build

WORKDIR /app

COPY services/ui/package.json services/ui/package-lock.json* ./
RUN npm install --no-audit --no-fund

COPY services/ui/ ./
# Generate typed OpenAPI client off the committed snapshot, then build.
RUN npm run openapi-types && npm run build

# Stage 2 — nginx serving the static bundle + reverse proxying to arm-backend.
FROM nginx:1.27-alpine

# `update-ca-certificates` is in the `ca-certificates` package on Alpine.
RUN apk add --no-cache ca-certificates

COPY --from=build /app/dist /usr/share/nginx/html
COPY services/ui/nginx.conf /etc/nginx/conf.d/default.conf
COPY services/ui/docker-entrypoint.sh /docker-entrypoint-arm.sh
RUN chmod +x /docker-entrypoint-arm.sh

EXPOSE 443

ENTRYPOINT ["/docker-entrypoint-arm.sh"]
CMD ["nginx", "-g", "daemon off;"]
