# Docker Compose Integration Guide

## Quick Reference for compose.yml

### Development Configuration

```yaml
services:
  frontend:
    build:
      context: ./frontend
      target: development
    ports:
      - "5173:5173"
    environment:
      - VITE_API_URL=http://backend:8000
    volumes:
      - ./frontend:/app
      - /app/node_modules
    depends_on:
      - backend
    networks:
      - knowledge-mapper-network
```

### Production Configuration

```yaml
services:
  frontend:
    build:
      context: ./frontend
      target: production
    ports:
      - "80:80"
    depends_on:
      - backend
    networks:
      - knowledge-mapper-network
    restart: unless-stopped
```

## Environment Variables

| Variable | Description | Development | Production |
|----------|-------------|-------------|------------|
| `VITE_API_URL` | Backend API URL | `http://backend:8000` | `http://backend:8000` |

**Note**: The `backend` hostname works in Docker networks. For local development outside Docker, use `http://localhost:8000`.

## Port Mappings

- **Development**: `5173:5173` (Vite dev server)
- **Production**: `80:80` (nginx)

## Volume Mounts (Development Only)

```yaml
volumes:
  - ./frontend:/app              # Source code
  - /app/node_modules            # Preserve node_modules in container
```

## Health Check (Optional)

```yaml
services:
  frontend:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5173/"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

For production (nginx):
```yaml
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
```

## Complete Example

```yaml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    networks:
      - knowledge-mapper-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 3

  frontend:
    build:
      context: ./frontend
      target: development
    ports:
      - "5173:5173"
    environment:
      - VITE_API_URL=http://backend:8000
    volumes:
      - ./frontend:/app
      - /app/node_modules
    depends_on:
      backend:
        condition: service_healthy
    networks:
      - knowledge-mapper-network

networks:
  knowledge-mapper-network:
    driver: bridge
```

## Testing the Integration

1. Start services:
   ```bash
   docker-compose up --build
   ```

2. Verify frontend is running:
   ```bash
   curl http://localhost:5173
   ```

3. Check backend communication:
   - Open browser to http://localhost:5173
   - Health check component should display backend status

4. View logs:
   ```bash
   docker-compose logs -f frontend
   docker-compose logs -f backend
   ```

## Common Issues

### Frontend can't connect to backend
- Verify both services are on the same network
- Check `VITE_API_URL` environment variable
- Ensure backend service name matches URL (e.g., `backend:8000`)

### Hot reload not working
- Verify volume mounts are correct
- Check file permissions
- Ensure `usePolling: true` in vite.config.ts (already configured)

### Port conflicts
- Change host port: `"3000:5173"` instead of `"5173:5173"`
- Update port in browser URL accordingly

## Production Deployment

For production, use the production target:

```yaml
services:
  frontend:
    build:
      context: ./frontend
      target: production
    ports:
      - "80:80"
    environment:
      - VITE_API_URL=http://backend:8000
    restart: unless-stopped
```

Or use environment-specific files:
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```
