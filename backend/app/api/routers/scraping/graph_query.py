"""
Knowledge graph query endpoints.

This router handles graph query operations:
- Traversing the knowledge graph from a starting entity

Follows Single Responsibility Principle by focusing only on graph queries.
"""

import logging
from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import select

from app.api.dependencies.auth import CurrentUserWithTenant
from app.api.dependencies.tenant import TenantSession
from app.api.routers.scraping.helpers import get_entity_or_404
from app.models.extracted_entity import (
    EntityRelationship,
    ExtractedEntity,
)
from app.schemas.scraping import (
    GraphEdge,
    GraphNode,
    GraphQueryRequest,
    GraphQueryResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["scraping"])

# Type alias for tenant-aware database session dependency
DbSession = TenantSession


@router.post(
    "/graph/query",
    response_model=GraphQueryResponse,
    summary="Query knowledge graph",
    description="Query the knowledge graph starting from an entity.",
)
async def query_graph(
    request: GraphQueryRequest,
    user: CurrentUserWithTenant,
    db: DbSession,
) -> GraphQueryResponse:
    """
    Query the knowledge graph.

    Returns nodes and edges starting from the specified entity,
    traversing up to the specified depth.
    """
    # Verify starting entity exists
    await get_entity_or_404(db, request.entity_id, user.tenant_id)

    # For now, query from PostgreSQL
    # TODO: Query from Neo4j when available
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    visited: set[UUID] = set()

    async def traverse(entity_id: UUID, current_depth: int) -> None:
        if entity_id in visited or current_depth > request.depth:
            return
        if len(nodes) >= request.limit:
            return

        visited.add(entity_id)

        # Get entity
        result = await db.execute(
            select(ExtractedEntity).where(
                ExtractedEntity.id == entity_id,
                ExtractedEntity.tenant_id == UUID(user.tenant_id),
            )
        )
        entity = result.scalar_one_or_none()
        if not entity:
            return

        # Filter by entity type if specified
        if request.entity_types and entity.entity_type not in request.entity_types:
            return

        nodes.append(
            GraphNode(
                id=entity.id,
                entity_type=entity.entity_type,
                name=entity.name,
                properties=entity.properties,
            )
        )

        # Get relationships
        rel_query = select(EntityRelationship).where(
            EntityRelationship.tenant_id == UUID(user.tenant_id),
            (
                (EntityRelationship.source_entity_id == entity_id)
                | (EntityRelationship.target_entity_id == entity_id)
            ),
        )

        if request.relationship_types:
            rel_query = rel_query.where(
                EntityRelationship.relationship_type.in_(request.relationship_types)
            )

        rel_result = await db.execute(rel_query)
        relationships = rel_result.scalars().all()

        for rel in relationships:
            # Add edge
            edges.append(
                GraphEdge(
                    source=rel.source_entity_id,
                    target=rel.target_entity_id,
                    relationship_type=rel.relationship_type,
                    confidence=rel.confidence_score,
                )
            )

            # Traverse connected entity
            next_id = (
                rel.target_entity_id
                if rel.source_entity_id == entity_id
                else rel.source_entity_id
            )
            await traverse(next_id, current_depth + 1)

    await traverse(request.entity_id, 0)

    return GraphQueryResponse(
        nodes=nodes,
        edges=edges,
        total_nodes=len(nodes),
        total_edges=len(edges),
        truncated=len(nodes) >= request.limit,
    )
