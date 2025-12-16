"""
Factory for creating extraction service instances from provider configs.

This module provides a factory for instantiating extraction services
based on ExtractionProvider model configurations. It handles API key
decryption and service configuration.
"""

import logging
from uuid import UUID

from app.extraction.base import BaseExtractionService, ExtractionError
from app.models.extraction_provider import ExtractionProvider, ExtractionProviderType

logger = logging.getLogger(__name__)


class ProviderConfigError(ExtractionError):
    """Raised when provider configuration is invalid."""

    def __init__(self, message: str, provider_type: str | None = None):
        super().__init__(message, provider=provider_type)


class ExtractionProviderFactory:
    """Factory for creating extraction services from provider configs.

    This factory handles:
    - Decrypting API keys from provider config
    - Instantiating the appropriate service class
    - Passing configuration parameters

    Example:
        provider = await db.get(ExtractionProvider, provider_id)
        service = ExtractionProviderFactory.create_service(provider, tenant_id)
        result = await service.extract(content, page_url)
    """

    @staticmethod
    def create_service(
        provider: ExtractionProvider,
        tenant_id: UUID,
    ) -> BaseExtractionService:
        """Create an extraction service from a provider configuration.

        Args:
            provider: ExtractionProvider model instance
            tenant_id: Tenant ID for key decryption

        Returns:
            Configured extraction service instance

        Raises:
            ProviderConfigError: If configuration is invalid
        """
        config = provider.config.copy() if provider.config else {}

        # Decrypt API key if present and encrypted
        if "api_key" in config and config["api_key"]:
            from app.core.encryption import get_encryption_service

            encryption = get_encryption_service()
            api_key = config["api_key"]

            if encryption.is_encrypted(api_key):
                try:
                    config["api_key"] = encryption.decrypt(
                        api_key,
                        tenant_id,
                        field_name="api_key",
                    )
                except Exception as e:
                    logger.error(
                        "Failed to decrypt API key",
                        extra={
                            "provider_id": str(provider.id),
                            "provider_type": provider.provider_type.value,
                            "error": str(e),
                        },
                    )
                    raise ProviderConfigError(
                        f"Failed to decrypt API key: {e}",
                        provider_type=provider.provider_type.value,
                    )

        # Create service based on provider type
        if provider.provider_type == ExtractionProviderType.OLLAMA:
            return ExtractionProviderFactory._create_ollama_service(provider, config)

        elif provider.provider_type == ExtractionProviderType.OPENAI:
            return ExtractionProviderFactory._create_openai_service(provider, config)

        elif provider.provider_type == ExtractionProviderType.ANTHROPIC:
            return ExtractionProviderFactory._create_anthropic_service(provider, config)

        else:
            raise ProviderConfigError(
                f"Unknown provider type: {provider.provider_type}",
                provider_type=str(provider.provider_type),
            )

    @staticmethod
    def _create_ollama_service(
        provider: ExtractionProvider,
        config: dict,
    ) -> BaseExtractionService:
        """Create an Ollama extraction service.

        Args:
            provider: ExtractionProvider model
            config: Decrypted configuration dict

        Returns:
            OllamaExtractionService instance
        """
        from app.extraction.ollama_extractor import OllamaExtractionService

        base_url = config.get("base_url")
        model = provider.default_model or config.get("model")

        logger.info(
            "Creating Ollama extraction service",
            extra={
                "provider_id": str(provider.id),
                "base_url": base_url,
                "model": model,
            },
        )

        return OllamaExtractionService(
            base_url=base_url,
            model=model,
            timeout=provider.timeout_seconds,
        )

    @staticmethod
    def _create_openai_service(
        provider: ExtractionProvider,
        config: dict,
    ) -> BaseExtractionService:
        """Create an OpenAI extraction service.

        Args:
            provider: ExtractionProvider model
            config: Decrypted configuration dict

        Returns:
            OpenAIExtractionService instance

        Raises:
            ProviderConfigError: If api_key is missing
        """
        from app.extraction.openai_extractor import OpenAIExtractionService

        api_key = config.get("api_key")
        if not api_key:
            raise ProviderConfigError(
                "OpenAI provider requires api_key in config",
                provider_type="openai",
            )

        model = provider.default_model or config.get("model") or "gpt-4o"
        temperature = config.get("temperature", 0.1)

        logger.info(
            "Creating OpenAI extraction service",
            extra={
                "provider_id": str(provider.id),
                "model": model,
            },
        )

        return OpenAIExtractionService(
            api_key=api_key,
            model=model,
            timeout=provider.timeout_seconds,
            max_context_length=provider.max_context_length,
            temperature=temperature,
        )

    @staticmethod
    def _create_anthropic_service(
        provider: ExtractionProvider,
        config: dict,
    ) -> BaseExtractionService:
        """Create an Anthropic extraction service.

        Args:
            provider: ExtractionProvider model
            config: Decrypted configuration dict

        Returns:
            Anthropic extraction service instance

        Raises:
            NotImplementedError: Anthropic integration not yet complete
        """
        # TODO: Integrate the existing llm_extractor.py for Anthropic
        raise NotImplementedError(
            "Anthropic extraction provider is not yet fully integrated. "
            "Use Ollama or OpenAI providers."
        )

    @staticmethod
    def get_supported_provider_types() -> list[str]:
        """Return list of supported provider types.

        Returns:
            List of provider type strings
        """
        return [t.value for t in ExtractionProviderType]

    @staticmethod
    def validate_config(
        provider_type: ExtractionProviderType,
        config: dict,
    ) -> list[str]:
        """Validate provider configuration.

        Args:
            provider_type: Type of provider
            config: Configuration dict to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if provider_type == ExtractionProviderType.OPENAI:
            if not config.get("api_key"):
                errors.append("api_key is required for OpenAI provider")

        elif provider_type == ExtractionProviderType.ANTHROPIC:
            if not config.get("api_key"):
                errors.append("api_key is required for Anthropic provider")

        elif provider_type == ExtractionProviderType.OLLAMA:
            # Ollama can use defaults from settings
            pass

        return errors
