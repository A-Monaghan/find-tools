# Static UIkit frontend — no build step; serves HTML/JS.
# Uses UIkit from CDN by default. Run setup-uikit.sh first to bundle local UIkit.
FROM nginx:alpine

COPY index.html app.js /usr/share/nginx/html/
# vendor/ holds local UIkit if setup-uikit.sh was run; else index.html falls back to CDN
COPY vendor /usr/share/nginx/html/vendor

# Reuse same nginx config as React frontend (API proxy, SPA fallback)
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
