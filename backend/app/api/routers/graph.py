"""
Knowledge graph query API endpoints.

This router provides endpoints for:
- Querying the knowledge graph (Neo4j)
- Retrieving graph data for visualization
"""

import logging
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import CurrentUserWithTenant
from app.api.dependencies.tenant import TenantSession
from app.models.extracted_entity import (
    EntityRelationship,
    EntityType,
    ExtractedEntity,
)
from app.schemas.scraping import (
    GraphQueryResponse,
    GraphNode,
    GraphEdge,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graph", tags=["graph"])


# Type alias for tenant-aware database session dependency
DbSession = TenantSession


@router.get(
    "/query",
    response_model=GraphQueryResponse,
    summary="Query knowledge graph",
    description="Query the knowledge graph, optionally centered on a specific entity.",
)
async def query_graph(
    user: CurrentUserWithTenant,
    db: DbSession,
    entity_id: Optional[UUID] = Query(
        None,
        description="Central entity ID to query around",
    ),
    depth: int = Query(
        2,
        ge=1,
        le=5,
        description="Relationship depth to traverse",
    ),
    entity_types: Optional[list[str]] = Query(
        None,
        description="Filter by entity types",
    ),
    limit: int = Query(
        100,
        ge=1,
        le=1000,
        description="Maximum nodes to return",
    ),
) -> GraphQueryResponse:
    """
    Query the knowledge graph for nodes and edges.

    If entity_id is provided, returns the subgraph around that entity.
    Otherwise, returns a sample of entities in the tenant's graph.
    """
    tenant_id = UUID(user.tenant_id)

    # Build base query for entities
    entity_query = select(ExtractedEntity).where(
        ExtractedEntity.tenant_id == tenant_id
    )

    # Filter by entity types if specified
    if entity_types:
        # Convert string types to enum values
        type_enums = []
        for t in entity_types:
            try:
                type_enums.append(EntityType(t))
            except ValueError:
                pass  # Ignore invalid types
        if type_enums:
            entity_query = entity_query.where(
                ExtractedEntity.entity_type.in_(type_enums)
            )

    # If centered on an entity, we need to find connected entities
    if entity_id:
        # Get the center entity first
        center_result = await db.execute(
            select(ExtractedEntity).where(
                ExtractedEntity.id == entity_id,
                ExtractedEntity.tenant_id == tenant_id,
            )
        )
        center_entity = center_result.scalar_one_or_none()
        if not center_entity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Entity not found",
            )

        # Get relationships for the center entity (both directions)
        rel_query = select(EntityRelationship).where(
            EntityRelationship.tenant_id == tenant_id,
            (
                (EntityRelationship.source_entity_id == entity_id) |
                (EntityRelationship.target_entity_id == entity_id)
            ),
        )
        rel_result = await db.execute(rel_query)
        relationships = rel_result.scalars().all()

        # Collect connected entity IDs
        connected_ids = {entity_id}
        for rel in relationships:
            connected_ids.add(rel.source_entity_id)
            connected_ids.add(rel.target_entity_id)

        # Get all connected entities
        entity_query = entity_query.where(
            ExtractedEntity.id.in_(connected_ids)
        )

    # Apply limit
    entity_query = entity_query.limit(limit)

    # Execute query
    result = await db.execute(entity_query)
    entities = result.scalars().all()

    if not entities:
        return GraphQueryResponse(
            nodes=[],
            edges=[],
            total_nodes=0,
            total_edges=0,
            truncated=False,
        )

    # Get entity IDs for relationship query
    entity_ids = [e.id for e in entities]

    # Get relationships between these entities
    rel_query = select(EntityRelationship).where(
        EntityRelationship.tenant_id == tenant_id,
        EntityRelationship.source_entity_id.in_(entity_ids),
        EntityRelationship.target_entity_id.in_(entity_ids),
    )
    rel_result = await db.execute(rel_query)
    relationships = rel_result.scalars().all()

    # Convert to response format
    nodes = [
        GraphNode(
            id=e.id,
            entity_type=e.entity_type,
            name=e.name,
            properties=e.properties or {},
        )
        for e in entities
    ]

    edges = [
        GraphEdge(
            source=r.source_entity_id,
            target=r.target_entity_id,
            relationship_type=r.relationship_type,
            confidence=r.confidence_score,
        )
        for r in relationships
    ]

    # Count totals for truncation check
    total_count_query = select(ExtractedEntity.id).where(
        ExtractedEntity.tenant_id == tenant_id
    )
    total_result = await db.execute(total_count_query)
    total_entities = len(total_result.all())

    truncated = len(entities) < total_entities and len(entities) >= limit

    return GraphQueryResponse(
        nodes=nodes,
        edges=edges,
        total_nodes=len(nodes),
        total_edges=len(edges),
        truncated=truncated,
    )
