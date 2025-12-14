"""
Example Todos API endpoints demonstrating authenticated and public routes.

This router provides example endpoints for:
- Public: Get public todos (no auth required)
- Protected: CRUD operations on user todos (auth required)
"""

from typing import Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies.auth import CurrentUserWithTenant

router = APIRouter(prefix="/todos", tags=["todos"])


# Schemas
class TodoBase(BaseModel):
    """Base todo schema."""
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    completed: bool = False


class TodoCreate(TodoBase):
    """Schema for creating a todo."""
    pass


class TodoUpdate(BaseModel):
    """Schema for updating a todo."""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    completed: Optional[bool] = None


class TodoResponse(TodoBase):
    """Schema for todo response."""
    id: str
    user_id: str
    tenant_id: str
    created_at: str
    updated_at: str


class PublicTodoResponse(BaseModel):
    """Schema for public todo response (no user info)."""
    id: str
    title: str
    description: Optional[str] = None
    completed: bool
    created_at: str


# In-memory storage for demo purposes
# In a real app, this would use a database
_demo_todos: dict[str, dict] = {
    "public-1": {
        "id": "public-1",
        "title": "Learn FastAPI",
        "description": "Complete the FastAPI tutorial",
        "completed": True,
        "created_at": "2024-01-01T00:00:00Z",
    },
    "public-2": {
        "id": "public-2",
        "title": "Build a Todo App",
        "description": "Create a full-stack todo application",
        "completed": False,
        "created_at": "2024-01-02T00:00:00Z",
    },
    "public-3": {
        "id": "public-3",
        "title": "Add Authentication",
        "description": "Integrate Keycloak OIDC authentication",
        "completed": False,
        "created_at": "2024-01-03T00:00:00Z",
    },
}

_user_todos: dict[str, dict[str, dict]] = {}


# Public endpoints (no auth required)
@router.get(
    "/public",
    response_model=list[PublicTodoResponse],
    summary="Get public todos",
    description="Returns a list of public example todos. No authentication required.",
)
async def get_public_todos() -> list[dict]:
    """
    Get public example todos.

    This endpoint is public and does not require authentication.
    It returns a static list of example todos.
    """
    return list(_demo_todos.values())


@router.get(
    "/public/{todo_id}",
    response_model=PublicTodoResponse,
    summary="Get a public todo",
    description="Returns a specific public todo by ID. No authentication required.",
)
async def get_public_todo(todo_id: str) -> dict:
    """
    Get a specific public todo.

    This endpoint is public and does not require authentication.
    """
    if todo_id not in _demo_todos:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Todo not found",
        )
    return _demo_todos[todo_id]


# Protected endpoints (auth required)
@router.get(
    "/",
    response_model=list[TodoResponse],
    summary="Get user todos",
    description="Returns all todos for the authenticated user.",
)
async def get_todos(user: CurrentUserWithTenant) -> list[dict]:
    """
    Get all todos for the authenticated user.

    Requires authentication. Returns only todos belonging to the current user
    within their tenant.
    """
    user_key = f"{user.tenant_id}:{user.user_id}"
    user_todos = _user_todos.get(user_key, {})
    return list(user_todos.values())


@router.post(
    "/",
    response_model=TodoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a todo",
    description="Creates a new todo for the authenticated user.",
)
async def create_todo(todo: TodoCreate, user: CurrentUserWithTenant) -> dict:
    """
    Create a new todo.

    Requires authentication. The todo is associated with the current user
    and their tenant.
    """
    user_key = f"{user.tenant_id}:{user.user_id}"

    if user_key not in _user_todos:
        _user_todos[user_key] = {}

    import uuid
    todo_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + "Z"

    new_todo = {
        "id": todo_id,
        "title": todo.title,
        "description": todo.description,
        "completed": todo.completed,
        "user_id": user.user_id,
        "tenant_id": user.tenant_id,
        "created_at": now,
        "updated_at": now,
    }

    _user_todos[user_key][todo_id] = new_todo
    return new_todo


@router.get(
    "/{todo_id}",
    response_model=TodoResponse,
    summary="Get a todo",
    description="Returns a specific todo by ID.",
)
async def get_todo(todo_id: str, user: CurrentUserWithTenant) -> dict:
    """
    Get a specific todo by ID.

    Requires authentication. Returns 404 if the todo doesn't exist
    or doesn't belong to the current user.
    """
    user_key = f"{user.tenant_id}:{user.user_id}"
    user_todos = _user_todos.get(user_key, {})

    if todo_id not in user_todos:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Todo not found",
        )

    return user_todos[todo_id]


@router.put(
    "/{todo_id}",
    response_model=TodoResponse,
    summary="Update a todo",
    description="Updates a specific todo by ID.",
)
async def update_todo(todo_id: str, todo: TodoUpdate, user: CurrentUserWithTenant) -> dict:
    """
    Update a specific todo by ID.

    Requires authentication. Returns 404 if the todo doesn't exist
    or doesn't belong to the current user.
    """
    user_key = f"{user.tenant_id}:{user.user_id}"
    user_todos = _user_todos.get(user_key, {})

    if todo_id not in user_todos:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Todo not found",
        )

    existing = user_todos[todo_id]

    if todo.title is not None:
        existing["title"] = todo.title
    if todo.description is not None:
        existing["description"] = todo.description
    if todo.completed is not None:
        existing["completed"] = todo.completed

    existing["updated_at"] = datetime.utcnow().isoformat() + "Z"

    return existing


@router.delete(
    "/{todo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a todo",
    description="Deletes a specific todo by ID.",
)
async def delete_todo(todo_id: str, user: CurrentUserWithTenant) -> None:
    """
    Delete a specific todo by ID.

    Requires authentication. Returns 404 if the todo doesn't exist
    or doesn't belong to the current user.
    """
    user_key = f"{user.tenant_id}:{user.user_id}"
    user_todos = _user_todos.get(user_key, {})

    if todo_id not in user_todos:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Todo not found",
        )

    del _user_todos[user_key][todo_id]
