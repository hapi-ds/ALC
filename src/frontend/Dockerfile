# AlcoaBase Frontend - Multi-stage Dockerfile
# Builds React/Vite app and serves via nginx with SPA routing.

# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: Builder — install deps and build static assets
# ─────────────────────────────────────────────────────────────────────────────
FROM node:22-alpine AS builder

WORKDIR /build

# Copy dependency files first for layer caching
COPY package.json package-lock.json ./

# Install dependencies
RUN npm ci

# Copy application source
COPY . .

# Build production assets
RUN npm run build

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: Runtime — serve with nginx
# ─────────────────────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS runtime

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Add custom nginx config for SPA routing
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets from builder stage
COPY --from=builder /build/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
