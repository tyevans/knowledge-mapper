"""
Database models.

This module exports all database models for easy import throughout the
application. All models inherit from Base and include common audit columns
(id, created_at, updated_at).

Models:
    - Tenant: Organization or tenant in the multi-tenant system
    - User: User within a tenant, authenticated via OAuth
    - OAuthProvider: OAuth provider configuration for a tenant
    - ProviderType: Enum of supported OAuth provider types
    - UserTenantMembership: User membership in a tenant (multi-tenant support)
    - MembershipRole: Enum of membership roles
    - ScrapingJob: Web scraping job configuration and status
    - JobStatus: Enum of scraping job states
    - ScrapedPage: Scraped web page content and metadata
    - ExtractedEntity: Entity extracted from scraped content
    - EntityType: Enum of entity types
    - ExtractionMethod: Enum of extraction methods
    - EntityRelationship: Relationship between entities
    - InferenceProvider: LLM inference provider configuration
    - InferenceProviderType: Enum of inference provider types
    - InferenceRequest: Inference request history (projection)
    - InferenceStatus: Enum of inference request statuses
"""

from app.models.extracted_entity import (
    EntityRelationship,
    EntityType,
    ExtractedEntity,
    ExtractionMethod,
)
from app.models.inference_provider import (
    InferenceProvider,
    ProviderType as InferenceProviderType,
)
from app.models.inference_request import InferenceRequest, InferenceStatus
from app.models.oauth_provider import OAuthProvider, ProviderType
from app.models.scraped_page import ScrapedPage
from app.models.scraping_job import JobStatus, ScrapingJob
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_tenant_membership import MembershipRole, UserTenantMembership

__all__ = [
    # Core models
    "Tenant",
    "User",
    "OAuthProvider",
    "ProviderType",
    "UserTenantMembership",
    "MembershipRole",
    # Scraping models
    "ScrapingJob",
    "JobStatus",
    "ScrapedPage",
    "ExtractedEntity",
    "EntityType",
    "ExtractionMethod",
    "EntityRelationship",
    # Inference models
    "InferenceProvider",
    "InferenceProviderType",
    "InferenceRequest",
    "InferenceStatus",
]
