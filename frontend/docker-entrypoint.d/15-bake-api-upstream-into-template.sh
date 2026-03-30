#!/bin/sh
set -e
# Write /etc/nginx/templates/default.conf.template from .pristine before 20-envsubst runs.
# Why: the stock envsubst step only substitutes a subset of container env vars. If
# ${NGINX_PROXY_API_UPSTREAM} is left in the file, nginx treats it as a variable name and
# proxy_pass gets "" → "invalid URL prefix" / 500 on /api/* (direct wget to backend still works).

if [ -z "${NGINX_PROXY_API_UPSTREAM:-}" ]; then
	export NGINX_PROXY_API_UPSTREAM="http://backend:8000"
fi
export NGINX_PROXY_API_UPSTREAM="${NGINX_PROXY_API_UPSTREAM%/}"

PRISTINE="/etc/nginx/templates/default.conf.template.pristine"
OUT="/etc/nginx/templates/default.conf.template"
test -f "$PRISTINE" || exit 0

sed "s|__NGINX_PROXY_API_UPSTREAM__|${NGINX_PROXY_API_UPSTREAM}|g" "$PRISTINE" > "${OUT}.new"
mv "${OUT}.new" "$OUT"
