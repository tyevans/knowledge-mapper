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

    # Build base query for entities - only canonical (not merged) entities
    entity_query = select(ExtractedEntity).where(
        ExtractedEntity.tenant_id == tenant_id,
        ExtractedEntity.is_canonical == True,  # noqa: E712
    )

    # Filter by entity types if specified
    # entity_type is now a string column, so filter directly
    if entity_types:
        # Normalize to lowercase for consistent matching
        normalized_types = [t.lower() for t in entity_types]
        entity_query = entity_query.where(
            ExtractedEntity.entity_type.in_(normalized_types)
        )

    # If centered on an entity, we need to find connected entities
    if entity_id:
        # Get the center entity first (must be canonical)
        center_result = await db.execute(
            select(ExtractedEntity).where(
                ExtractedEntity.id == entity_id,
                ExtractedEntity.tenant_id == tenant_id,
                ExtractedEntity.is_canonical == True,  # noqa: E712
            )
        )
        center_entity = center_result.scalar_one_or_none()
        if not center_entity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Entity not found or has been merged",
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

    # Get canonical entity IDs
    canonical_ids = [e.id for e in entities]
    canonical_id_set = set(canonical_ids)

    # Find all merged entities that point to these canonical entities
    # so we can include their relationships too
    merged_query = select(ExtractedEntity).where(
        ExtractedEntity.tenant_id == tenant_id,
        ExtractedEntity.is_canonical == False,  # noqa: E712
        ExtractedEntity.is_alias_of.in_(canonical_ids),
    )
    merged_result = await db.execute(merged_query)
    merged_entities = merged_result.scalars().all()

    # Build a mapping from merged entity ID -> canonical entity ID
    merged_to_canonical: dict[UUID, UUID] = {}
    for merged in merged_entities:
        if merged.is_alias_of:
            merged_to_canonical[merged.id] = merged.is_alias_of

    # All entity IDs to query relationships for (canonical + merged)
    all_entity_ids = list(canonical_id_set | set(merged_to_canonical.keys()))

    # Get relationships between any of these entities
    rel_query = select(EntityRelationship).where(
        EntityRelationship.tenant_id == tenant_id,
        EntityRelationship.source_entity_id.in_(all_entity_ids),
        EntityRelationship.target_entity_id.in_(all_entity_ids),
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

    # Build edges, remapping merged entity IDs to their canonical counterparts
    edges = []
    seen_edges: set[tuple[UUID, UUID, str]] = set()  # Deduplicate edges
    for r in relationships:
        # Remap source and target to canonical IDs
        source_id = merged_to_canonical.get(r.source_entity_id, r.source_entity_id)
        target_id = merged_to_canonical.get(r.target_entity_id, r.target_entity_id)

        # Only include edges where both ends are in our canonical set
        if source_id not in canonical_id_set or target_id not in canonical_id_set:
            continue

        # Skip self-loops that may result from merging
        if source_id == target_id:
            continue

        # Deduplicate edges (same source, target, type)
        edge_key = (source_id, target_id, r.relationship_type)
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)

        edges.append(
            GraphEdge(
                source=source_id,
                target=target_id,
                relationship_type=r.relationship_type,
                confidence=r.confidence_score,
            )
        )

    # Count totals for truncation check (only canonical entities)
    total_count_query = select(ExtractedEntity.id).where(
        ExtractedEntity.tenant_id == tenant_id,
        ExtractedEntity.is_canonical == True,  # noqa: E712
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
