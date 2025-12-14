# Knowledge Mapper - Backend

FastAPI-based backend service for Knowledge Mapper.

## Technology Stack

- **Python 3.13**: Modern Python with latest features
- **FastAPI**: High-performance async web framework
- **Uvicorn**: ASGI server with hot-reload support
- **Pydantic**: Data validation and settings management
- **PostgreSQL**: Primary database (via asyncpg)
- **SQLAlchemy**: Async ORM for database operations

## Project Structure

```
backend/
├── app/
│   ├── api/
│   │   └── routers/        # API route handlers
│   │       └── health.py   # Health check endpoints
│   ├── core/               # Core configuration and utilities
│   │   └── config.py       # Settings and configuration
│   ├── models/             # SQLAlchemy models
│   ├── schemas/            # Pydantic schemas
│   └── services/           # Business logic services
├── tests/                  # Unit and integration tests
├── alembic/                # Database migrations
├── main.py                 # Application entry point
├── pyproject.toml          # Project metadata, dependencies, and tool config
├── Dockerfile              # Container image definition
└── .dockerignore          # Docker build exclusions
```

## Getting Started

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) - Fast Python package installer and resolver

Install uv:
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or with pip
pip install uv
```

### Local Development (without Docker)

1. Install dependencies with uv:
```bash
uv sync
```

This will create a virtual environment and install all dependencies from `pyproject.toml`.

2. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. Run the development server:
```bash
uv run dev
```

Or activate the virtual environment and run directly:
```bash
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`

### Available Commands

With uv, you can run scripts defined in `pyproject.toml`:

```bash
# Development
uv run dev              # Start dev server with hot-reload
uv run test             # Run tests
uv run test-cov         # Run tests with coverage
uv run lint             # Check code with ruff
uv run lint-fix         # Fix linting issues
uv run format           # Format code with ruff
uv run format-check     # Check code formatting

# Database migrations
uv run db-migrate       # Apply migrations
uv run db-rollback      # Rollback last migration
uv run db-revision      # Create new migration
uv run db-history       # View migration history

# Utilities
uv run clean            # Clean cache files
```

### Docker Development

Build and run with Docker:
```bash
docker build --target development -t knowledge-mapper-backend:dev .
docker run -p 8000:8000 -v $(pwd):/app knowledge-mapper-backend:dev
```

Or use Docker Compose (recommended):
```bash
docker-compose up backend
```

## API Endpoints

### Health & Status
- `GET /health` - Basic health check
- `GET /ready` - Readiness probe
- `GET /` - API information

### Documentation
- `GET /docs` - Interactive Swagger UI documentation
- `GET /redoc` - ReDoc documentation
- `GET /openapi.json` - OpenAPI schema

## Configuration

Configuration is managed through environment variables. See `.env.example` for available options:

- `APP_NAME`: Application name (default: "Knowledge Mapper")
- `APP_VERSION`: Application version
- `DEBUG`: Enable debug mode (default: true)
- `API_V1_PREFIX`: API route prefix (default: "/api/v1")
- `CORS_ORIGINS`: Allowed CORS origins (comma-separated)
- `DATABASE_URL`: PostgreSQL connection string
- `HOST`: Server host (default: "0.0.0.0")
- `PORT`: Server port (default: 8000)

## Running Tests

Run all tests:
```bash
uv run test
```

Run with coverage:
```bash
uv run test-cov
```

Run specific test file:
```bash
uv run pytest tests/test_health.py
```

Or with the virtual environment activated:
```bash
pytest tests/test_health.py
```

## Development Guidelines

### Code Style
- Follow PEP 8 guidelines
- Use type hints extensively
- Use ruff for linting: `uv run lint`
- Format code with: `uv run format`

### Testing
- Write unit tests for all new features
- Maintain test coverage above 80%
- Use pytest fixtures for test setup

### API Design
- Use Pydantic models for request/response validation
- Follow RESTful conventions
- Return appropriate HTTP status codes
- Include comprehensive error messages

## Architecture Patterns

This backend follows event sourcing and CQRS patterns:

- **Commands**: Write operations that modify state
- **Queries**: Read operations that fetch data
- **Events**: Immutable records of state changes
- **Handlers**: Process commands and queries

## OAuth 2.0 Scope Enforcement

The backend enforces fine-grained permissions using OAuth 2.0 scopes. Scopes control what operations users can perform based on the principle of least privilege.

### Available Scopes

- **statements/read**: Read all xAPI statements in the tenant
- **statements/write**: Write xAPI statements
- **statements/read/mine**: Read only the user's own xAPI statements
- **state/read**: Read xAPI state resources
- **state/write**: Write xAPI state resources
- **admin**: System-wide administrative access
- **tenant/admin**: Tenant-level administrative access

### Protecting Endpoints

Use `require_scopes()` or `require_any_scope()` dependencies to protect API endpoints:

```python
from fastapi import APIRouter, Depends
from app.api.dependencies.auth import CurrentUser
from app.api.dependencies.scopes import require_scopes, require_any_scope
from app.schemas.auth import SCOPE_STATEMENTS_WRITE, SCOPE_STATEMENTS_READ, SCOPE_STATEMENTS_READ_MINE

router = APIRouter()

# Require single scope (write access)
@router.post("/statements")
async def post_statement(
    statement: dict,
    current_user: CurrentUser,
    _: None = Depends(require_scopes(SCOPE_STATEMENTS_WRITE))
):
    return {"status": "created", "id": "statement-123"}

# Require multiple scopes (AND logic - all required)
@router.delete("/admin/tenants/{tenant_id}")
async def delete_tenant(
    tenant_id: str,
    current_user: CurrentUser,
    _: None = Depends(require_scopes("admin", "tenant/admin"))
):
    return {"status": "deleted"}

# Require any scope (OR logic - at least one required)
@router.get("/statements")
async def get_statements(
    current_user: CurrentUser,
    _: None = Depends(require_any_scope(SCOPE_STATEMENTS_READ, SCOPE_STATEMENTS_READ_MINE))
):
    # User has either full read access OR read/mine
    # Can differentiate behavior based on scope
    if current_user.has_scope(SCOPE_STATEMENTS_READ):
        return all_statements  # Full access
    else:
        return user_statements  # Own statements only
```

### Conditional Logic with Helper Functions

Use helper functions for conditional scope checking within route handlers:

```python
from app.api.dependencies.scopes import has_scope, has_any_scope, has_all_scopes

@router.get("/statements/{statement_id}")
async def get_statement(
    statement_id: str,
    current_user: CurrentUser,
):
    # Conditional logic based on scope
    if has_scope(current_user, SCOPE_STATEMENTS_WRITE):
        # Allow edit operations
        return {"statement": statement, "editable": True}
    else:
        # Read-only
        return {"statement": statement, "editable": False}

# Check for any of multiple scopes
if has_any_scope(current_user, "admin", "tenant/admin"):
    show_admin_controls = True

# Check for all of multiple scopes
if has_all_scopes(current_user, SCOPE_STATEMENTS_WRITE, SCOPE_STATE_WRITE):
    enable_full_edit = True
```

### Error Responses

When a user lacks required scopes, the API returns a 403 Forbidden response following OAuth 2.0 error format:

```json
{
  "error": "insufficient_scope",
  "error_description": "Missing required scopes: statements/write",
  "required_scopes": ["statements/write"],
  "missing_scopes": ["statements/write"]
}
```

### Testing Scope Enforcement

Run scope enforcement unit tests:

```bash
pytest tests/unit/test_scope_enforcement.py -v
```

The test suite includes 32 comprehensive test cases covering:
- AND logic (require_scopes)
- OR logic (require_any_scope)
- Helper functions (has_scope, has_any_scope, has_all_scopes)
- Error message format validation
- Edge cases

## Next Steps

- Database migrations setup
- Authentication and authorization
- Event sourcing infrastructure
- CQRS command/query handlers
- WebSocket support for real-time updates
- Logging and monitoring integration
