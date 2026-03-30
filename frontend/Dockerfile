# Build on Debian slim (glibc), not Alpine: esbuild/Rollup prebuilds align with most CI images;
# Alpine/musl occasionally breaks or needs extra build deps on hosted builders.
# Runtime image below stays nginx:alpine (small).
FROM node:22-bookworm-slim AS builder

# For Fly / GH Actions: pass VITE_API_BASE_URL so the SPA calls the public API (CORS on backend).
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
# Vite bundling many modules can hit default heap on small build VMs.
ENV NODE_OPTIONS=--max-old-space-size=4096

WORKDIR /app

COPY package.json package-lock.json ./
# Reproducible install; fails if lockfile does not match package.json (surfaces drift early).
RUN npm ci

COPY . .
RUN npm run build

# Production stage — template is envsubst'd at container start (see nginx docker-entrypoint).
# Default matches docker-compose service name "backend". On Northflank/K8s, set NGINX_PROXY_API_UPSTREAM
# to your backend base URL, e.g. https://api-xxxxx.northflank.app/ (include trailing slash).
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
# Pristine only; 15-bake-api-upstream-into-template.sh writes default.conf.template before envsubst.
COPY default.conf.template /etc/nginx/templates/default.conf.template.pristine
COPY docker-entrypoint.d/14-dns-resolver-for-proxy.envsh /docker-entrypoint.d/14-dns-resolver-for-proxy.envsh
COPY docker-entrypoint.d/15-bake-api-upstream-into-template.sh /docker-entrypoint.d/15-bake-api-upstream-into-template.sh
RUN chmod +x /docker-entrypoint.d/14-dns-resolver-for-proxy.envsh \
	&& chmod +x /docker-entrypoint.d/15-bake-api-upstream-into-template.sh
# No trailing slash (14 script strips if present). On Northflank set to internal http://<svc>:8000 or public https://…/code.run
ENV NGINX_PROXY_API_UPSTREAM=http://backend:8000
ENV NGINX_RESOLVER=

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]