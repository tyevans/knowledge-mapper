# Quick Start Guide - Backend

Get the Knowledge Mapper backend running in under 5 minutes.

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) - Fast Python package installer
- Docker (optional, for containerized deployment)

Install uv:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh  # macOS/Linux
# Or: pip install uv
```

## Option 1: Local Development (Fastest)

1. Navigate to backend directory:
```bash
cd backend
```

2. Install dependencies:
```bash
uv sync
```

3. Run the development server:
```bash
uv run dev
```

4. Access the API:
- API Root: http://localhost:8000
- Health Check: http://localhost:8000/api/v1/health
- Interactive Docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Option 2: Docker

1. Build the image:
```bash
make docker-build
# OR manually:
# docker build --target development -t knowledge-mapper-backend:dev .
```

2. Run the container:
```bash
make docker-run
# OR manually:
# docker run -p 8000:8000 -v $(pwd):/app knowledge-mapper-backend:dev
```

3. Access the API at http://localhost:8000

## Option 3: Docker Compose (Recommended for Full Stack)

Wait for the DevOps agent to complete the docker-compose.yml configuration, then:

```bash
docker-compose up backend
```

## Verify Installation

Run tests:
```bash
uv run test
```

Expected output: Tests should pass

## Available Endpoints

### Root
```bash
curl http://localhost:8000/
```

### Health Check
```bash
curl http://localhost:8000/api/v1/health
```

### Readiness Check
```bash
curl http://localhost:8000/api/v1/ready
```

## Common Commands

```bash
uv sync            # Install/update dependencies
uv run dev         # Run dev server
uv run test        # Run tests
uv run test-cov    # Run tests with coverage
uv run lint        # Run linter
uv run lint-fix    # Fix linting issues
uv run format      # Format code
uv run clean       # Clean temporary files
```

## Configuration

Copy the example environment file and customize:
```bash
cp .env.example .env
# Edit .env with your preferred settings
```

Key settings:
- `DEBUG`: Enable debug mode (default: true)
- `PORT`: Server port (default: 8000)
- `CORS_ORIGINS`: Allowed frontend origins
- `DATABASE_URL`: PostgreSQL connection string

## Next Steps

1. Explore the interactive API docs at http://localhost:8000/docs
2. Review the full README.md for detailed documentation
3. Check the project structure in the README
4. Start building additional features!

## Troubleshooting

### Port already in use
```bash
# Change the port in .env or run with custom port:
uv run uvicorn app.main:app --reload --port 8001
```

### Import errors
```bash
# Reinstall dependencies:
rm -rf .venv uv.lock
uv sync
```

### Tests failing
```bash
# Clean cache and rerun:
uv run clean
uv run test
```

## Need Help?

- Check the full README.md in this directory
- Review the implementation tracking document in docs/tasks/backend-foundation/
- Check FastAPI documentation: https://fastapi.tiangolo.com/
