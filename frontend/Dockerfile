# Multi-stage Dockerfile for Frontend

# Stage 1: Development
FROM node:20-alpine AS development

WORKDIR /app

# Copy package files and entrypoint
COPY package*.json ./
COPY docker-entrypoint.sh /usr/local/bin/

# Make entrypoint executable
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Install dependencies (will be overwritten by volume mount, but provides fallback)
RUN npm install

# Copy source code
COPY . .

# Expose Vite dev server port
EXPOSE 5173

# Use entrypoint to ensure node_modules are installed
ENTRYPOINT ["docker-entrypoint.sh"]

# Start development server with hot reload
CMD ["npm", "run", "dev"]

# Stage 2: Build
FROM node:20-alpine AS build

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy source code
COPY . .

# Build the application
RUN npm run build

# Stage 3: Production
FROM nginx:alpine AS production

# OCI Labels for container metadata
# See: https://github.com/opencontainers/image-spec/blob/main/annotations.md
LABEL org.opencontainers.image.title="Knowledge Mapper Frontend"
LABEL org.opencontainers.image.description="Lit web components frontend for Knowledge Mapper"
LABEL org.opencontainers.image.vendor="Tyler Evans"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.source="https://github.com/your-github-username/knowledge-mapper"

# Create non-root user and configure nginx directories for non-root operation
# Using UID/GID 1000 for compatibility with host user mapping
RUN addgroup -g 1000 -S appgroup && \
    adduser -u 1000 -S appuser -G appgroup && \
    mkdir -p /var/cache/nginx /var/run/nginx /var/log/nginx && \
    chown -R appuser:appgroup /var/cache/nginx /var/run/nginx /var/log/nginx /usr/share/nginx/html && \
    touch /var/run/nginx.pid && \
    chown appuser:appgroup /var/run/nginx.pid

# Copy custom nginx.conf (configured for non-root on port 8080)
COPY --chown=appuser:appgroup nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets from build stage with correct ownership
COPY --from=build --chown=appuser:appgroup /app/dist /usr/share/nginx/html

# Switch to non-root user (security best practice)
USER appuser

# Expose non-privileged port (8080 for non-root operation)
EXPOSE 8080

# Health check configuration
# Aligns with Kubernetes probe patterns:
#   --interval=30s    -> periodSeconds: 30
#   --timeout=10s     -> timeoutSeconds: 10
#   --start-period=5s -> initialDelaySeconds: 5 (nginx starts faster than backend)
#   --retries=3       -> failureThreshold: 3
# Uses wget (pre-installed on Alpine, smaller than curl)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:8080/health || exit 1

# Start nginx in foreground mode
CMD ["nginx", "-g", "daemon off;"]
