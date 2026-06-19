# ────────────────────────────────────────────────────────
# Honestly Frontend — React Vite → Nginx
# Multi-stage: build with node:22-alpine, serve with nginx:alpine
# ────────────────────────────────────────────────────────

# ── Build stage ─────────────────────────────────────────
FROM node:22-alpine AS build

WORKDIR /app

# Copy dependency manifests first (Docker layer cache)
COPY package.json package-lock.json ./
RUN npm ci && npm cache clean --force

# Copy source and build
COPY . .
RUN npm run build

# ── Runtime stage ───────────────────────────────────────
FROM nginx:alpine

# Copy the built static files
COPY --from=build /app/dist /usr/share/nginx/html

# Copy custom nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port 80
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -sf http://localhost:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
