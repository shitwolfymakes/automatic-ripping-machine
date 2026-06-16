# Stage 1 — build the SvelteKit static bundle.
FROM node:26-slim AS build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
# api.gen.ts is committed; build consumes it directly (codegen needs the v3
# repo + snapshot, unavailable in the isolated build context).
RUN npm run build

# Stage 2 — nginx serving the static bundle + reverse-proxying to arm-backend.
FROM nginx:1.27-alpine
RUN apk add --no-cache ca-certificates
COPY --from=build /app/frontend/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY docker-entrypoint.sh /docker-entrypoint-arm.sh
RUN chmod +x /docker-entrypoint-arm.sh
EXPOSE 443
ENTRYPOINT ["/docker-entrypoint-arm.sh"]
CMD ["nginx", "-g", "daemon off;"]
