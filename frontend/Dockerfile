# ── Stage 1: Build React/Vite app ──────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files first (better layer caching)
COPY package.json package-lock.json* yarn.lock* pnpm-lock.yaml* ./

# Install dependencies (disable strict SSL for institutional proxies)
RUN npm config set strict-ssl false && (npm ci --prefer-offline 2>/dev/null || npm install)

# Accept build args for API URLs (injected by docker-compose)
ARG VITE_API_BASE_URL=http://localhost:8080
ARG VITE_WS_BASE_URL=ws://localhost:8080
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_WS_BASE_URL=$VITE_WS_BASE_URL

# Copy source and build
COPY . .
RUN npm run build

# ── Stage 2: Serve with nginx ───────────────────────────────────────────────────
FROM nginx:1.27-alpine AS runner

# Remove default nginx config and copy ours
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom nginx config if it exists (falls back to a minimal one)
COPY --from=builder /app/dist /usr/share/nginx/html

# Write a minimal nginx config for SPA serving
RUN printf 'server {\n\
    listen 80;\n\
    server_name _;\n\
    root /usr/share/nginx/html;\n\
    index index.html;\n\
    location /api/ {\n\
    proxy_pass http://api:8080;\n\
    proxy_http_version 1.1;\n\
    proxy_set_header Host $host;\n\
    proxy_set_header X-Real-IP $remote_addr;\n\
    proxy_read_timeout 120s;\n\
    proxy_buffering off;\n\
    }\n\
    location /ws/ {\n\
    proxy_pass http://api:8080;\n\
    proxy_http_version 1.1;\n\
    proxy_set_header Upgrade $http_upgrade;\n\
    proxy_set_header Connection "upgrade";\n\
    proxy_set_header Host $host;\n\
    proxy_read_timeout 3600s;\n\
    proxy_buffering off;\n\
    }\n\
    location / {\n\
    try_files $uri $uri/ /index.html;\n\
    }\n\
    location ~* \\.(js|css|png|jpg|ico|svg|woff2?)$ {\n\
    expires 1y;\n\
    add_header Cache-Control "public, immutable";\n\
    }\n\
    }\n' > /etc/nginx/conf.d/app.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
