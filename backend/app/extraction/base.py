"""
Base interface for extraction services.

All extraction providers must implement this interface to ensure
consistent behavior across Ollama, OpenAI, Anthropic, etc.
"""

from abc import ABC, abstractmethod
from typing import Protocol
from uuid import UUID

from app.extraction.schemas import ExtractionResult
from app.extraction.prompts import DocumentationType


class ExtractionServiceProtocol(Protocol):
    """Protocol defining extraction service interface.

    This protocol allows duck-typing for extraction services without
    requiring inheritance from a specific base class.
    """

    async def extract(
        self,
        content: str,
        page_url: str,
        max_length: int | None = None,
        doc_type: DocumentationType | None = None,
        additional_context: str | None = None,
        tenant_id: UUID | None = None,
    ) -> ExtractionResult:
        """Extract entities and relationships from content."""
        ...

    async def health_check(self) -> dict:
        """Check provider connectivity and availability."""
        ...


class BaseExtractionService(ABC):
    """Abstract base class for extraction services.

    All extraction provider implementations should inherit from this class
    to ensure consistent interface and behavior.

    Attributes:
        provider_name: Human-readable name of the provider (e.g., "ollama", "openai")
    """

    provider_name: str = "base"

    @abstractmethod
    async def extract(
        self,
        content: str,
        page_url: str,
        max_length: int | None = None,
        doc_type: DocumentationType | None = None,
        additional_context: str | None = None,
        tenant_id: UUID | None = None,
    ) -> ExtractionResult:
        """Extract entities and relationships from content.

        Args:
            content: The text content to analyze
            page_url: URL of the source page (for context)
            max_length: Maximum content length (truncate if exceeded)
            doc_type: Type of documentation for prompt optimization
            additional_context: Additional context to guide extraction
            tenant_id: Tenant ID for rate limiting

        Returns:
            ExtractionResult with entities and relationships

        Raises:
            ExtractionError: If extraction fails
        """
        pass

    @abstractmethod
    async def health_check(self) -> dict:
        """Check provider connectivity and availability.

        Returns:
            dict with health status information:
                - status: "healthy" or "unhealthy"
                - provider: Provider name
                - model: Configured model
                - error: Error message (if unhealthy)
        """
        pass


class ExtractionError(Exception):
    """Base exception for extraction errors.

    Attributes:
        message: Human-readable error message
        cause: Optional underlying exception
        provider: Name of the provider that raised the error
    """

    def __init__(
        self,
        message: str,
        cause: Exception | None = None,
        provider: str | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.cause = cause
        self.provider = provider

    def __str__(self) -> str:
        if self.provider:
            return f"[{self.provider}] {self.message}"
        return self.message
