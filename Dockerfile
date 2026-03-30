# syntax=docker/dockerfile:1
# Root-context image for Fly when fly.toml lives at repo root: root package.json only
# wires scripts; real deps live in frontend/. Without `npm install --prefix frontend`,
# `npm run build` fails with `tsc: not found`.
FROM node:22.21.1-slim AS base
WORKDIR /app

ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

FROM base AS build
RUN apt-get update -qq && apt-get install --no-install-recommends -y \
    build-essential node-gyp pkg-config python-is-python3 \
    && rm -rf /var/lib/apt/lists/*

# Layer cache: lockfiles first, then full install (tsc/vite live in frontend devDependencies)
COPY package.json ./
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN npm install && npm install --prefix frontend --include=dev

COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/frontend/dist /usr/share/nginx/html
COPY frontend/default.conf.template /etc/nginx/templates/default.conf.template.pristine
COPY frontend/docker-entrypoint.d/14-dns-resolver-for-proxy.envsh /docker-entrypoint.d/14-dns-resolver-for-proxy.envsh
COPY frontend/docker-entrypoint.d/15-bake-api-upstream-into-template.sh /docker-entrypoint.d/15-bake-api-upstream-into-template.sh
RUN chmod +x /docker-entrypoint.d/14-dns-resolver-for-proxy.envsh \
	&& chmod +x /docker-entrypoint.d/15-bake-api-upstream-into-template.sh
ENV NGINX_PROXY_API_UPSTREAM=http://backend:8000
ENV NGINX_RESOLVER=
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
