"""
Repository layer for data access abstraction.

This package contains repository implementations following the Repository pattern.
Each repository provides an abstraction over database operations for a specific
domain entity.

Benefits:
- Decouples business logic from data access details
- Centralizes query logic
- Makes code easier to test (repositories can be mocked)
- Follows Dependency Inversion Principle (DIP)

Usage:
    from app.repositories.extraction_provider import (
        ExtractionProviderRepository,
        ExtractionProviderRepo,
        get_extraction_provider_repository,
    )
"""

from app.repositories.extraction_provider import (
    ExtractionProviderRepository,
    ExtractionProviderRepo,
    ExtractionProviderNotFoundError,
    ExtractionProviderInactiveError,
    get_extraction_provider_repository,
)

__all__ = [
    "ExtractionProviderRepository",
    "ExtractionProviderRepo",
    "ExtractionProviderNotFoundError",
    "ExtractionProviderInactiveError",
    "get_extraction_provider_repository",
]
