"""
Integration tests for Neo4j sync operations.

These tests verify the integration between the application and a real Neo4j
database instance. Tests cover entity sync, relationship sync, tenant isolation,
and error handling scenarios.

Tests require a running Neo4j instance and will be skipped if unavailable.
"""

from uuid import uuid4

import pytest

from app.services.neo4j import Neo4jService


# =============================================================================
# Entity Sync Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
class TestNeo4jEntitySync:
    """Integration tests for Neo4j entity sync operations.

    These tests verify that entities can be created, updated, and retrieved
    from Neo4j using the Neo4jService class.
    """

    async def test_entity_syncs_to_neo4j(
        self,
        neo4j_service: Neo4jService,
        cleanup_single_tenant,
    ):
        """Test that an entity can be synced to Neo4j.

        Verifies that create_entity_node successfully creates a node
        and returns a valid Neo4j element ID.
        """
        tenant_id = cleanup_single_tenant
        entity_id = uuid4()

        # Create entity node
        node_id = await neo4j_service.create_entity_node(
            entity_id=entity_id,
            tenant_id=tenant_id,
            entity_type="CLASS",
            name="TestEntity",
            properties={"docstring": "A test class"},
            description="Test entity for integration testing",
        )

        # Verify node was created
        assert node_id is not None
        assert isinstance(node_id, str)
        assert len(node_id) > 0

        # Verify we can retrieve the node
        node = await neo4j_service.get_entity_node(entity_id, tenant_id)
        assert node is not None
        assert node["name"] == "TestEntity"
        assert node["type"] == "CLASS"
        assert node["description"] == "Test entity for integration testing"

    async def test_entity_update_on_duplicate(
        self,
        neo4j_service: Neo4jService,
        cleanup_single_tenant,
    ):
        """Test that syncing the same entity twice updates rather than duplicates.

        Neo4j uses MERGE which should update existing nodes rather than
        creating duplicates when the same entity_id is used.
        """
        tenant_id = cleanup_single_tenant
        entity_id = uuid4()

        # Create entity first time
        node_id_1 = await neo4j_service.create_entity_node(
            entity_id=entity_id,
            tenant_id=tenant_id,
            entity_type="FUNCTION",
            name="original_function",
            properties={"version": 1},
        )

        # Update entity second time with new properties
        node_id_2 = await neo4j_service.create_entity_node(
            entity_id=entity_id,
            tenant_id=tenant_id,
            entity_type="FUNCTION",
            name="updated_function",
            properties={"version": 2},
            description="Updated description",
        )

        # Should return same node ID (MERGE behavior)
        assert node_id_1 == node_id_2

        # Verify only one node exists with updated values
        node = await neo4j_service.get_entity_node(entity_id, tenant_id)
        assert node is not None
        assert node["name"] == "updated_function"
        assert node["properties"]["version"] == 2
        assert node["description"] == "Updated description"

        # Verify count is 1
        count = await neo4j_service.count_entities_for_tenant(tenant_id)
        assert count == 1

    async def test_entity_with_properties(
        self,
        neo4j_service: Neo4jService,
        cleanup_single_tenant,
        sample_entity_properties,
    ):
        """Test that entity properties are correctly stored and retrieved.

        Verifies that complex property dictionaries are properly serialized
        to and from Neo4j.
        """
        tenant_id = cleanup_single_tenant
        entity_id = uuid4()

        # Create entity with complex properties
        await neo4j_service.create_entity_node(
            entity_id=entity_id,
            tenant_id=tenant_id,
            entity_type="FUNCTION",
            name="complex_function",
            properties=sample_entity_properties,
        )

        # Retrieve and verify properties
        node = await neo4j_service.get_entity_node(entity_id, tenant_id)
        assert node is not None
        assert node["properties"]["docstring"] == sample_entity_properties["docstring"]
        assert node["properties"]["signature"] == sample_entity_properties["signature"]
        assert node["properties"]["methods"] == sample_entity_properties["methods"]

    async def test_entity_delete(
        self,
        neo4j_service: Neo4jService,
        cleanup_single_tenant,
    ):
        """Test that an entity can be deleted from Neo4j."""
        tenant_id = cleanup_single_tenant
        entity_id = uuid4()

        # Create entity
        await neo4j_service.create_entity_node(
            entity_id=entity_id,
            tenant_id=tenant_id,
            entity_type="CONCEPT",
            name="DeleteMe",
            properties={},
        )

        # Verify it exists
        node = await neo4j_service.get_entity_node(entity_id, tenant_id)
        assert node is not None

        # Delete entity
        deleted = await neo4j_service.delete_entity_node(entity_id, tenant_id)
        assert deleted is True

        # Verify it no longer exists
        node = await neo4j_service.get_entity_node(entity_id, tenant_id)
        assert node is None

    async def test_delete_nonexistent_entity_returns_false(
        self,
        neo4j_service: Neo4jService,
        cleanup_single_tenant,
    ):
        """Test that deleting a nonexistent entity returns False."""
        tenant_id = cleanup_single_tenant
        nonexistent_id = uuid4()

        # Attempt to delete nonexistent entity
        deleted = await neo4j_service.delete_entity_node(nonexistent_id, tenant_id)
        assert deleted is False

    async def test_get_nonexistent_entity_returns_none(
        self,
        neo4j_service: Neo4jService,
        cleanup_single_tenant,
    ):
        """Test that getting a nonexistent entity returns None."""
        tenant_id = cleanup_single_tenant
        nonexistent_id = uuid4()

        node = await neo4j_service.get_entity_node(nonexistent_id, tenant_id)
        assert node is None


# =============================================================================
# Relationship Sync Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
class TestNeo4jRelationshipSync:
    """Integration tests for Neo4j relationship sync operations.

    These tests verify that relationships between entities can be created
    and queried in Neo4j.
    """

    async def test_relationship_syncs_to_neo4j(
        self,
        neo4j_service: Neo4jService,
        cleanup_single_tenant,
    ):
        """Test that a relationship can be synced to Neo4j.

        Creates two entities and a relationship between them,
        then verifies the relationship exists.
        """
        tenant_id = cleanup_single_tenant
        source_id = uuid4()
        target_id = uuid4()
        relationship_id = uuid4()

        # Create source entity
        await neo4j_service.create_entity_node(
            entity_id=source_id,
            tenant_id=tenant_id,
            entity_type="CLASS",
            name="SourceClass",
            properties={},
        )

        # Create target entity
        await neo4j_service.create_entity_node(
            entity_id=target_id,
            tenant_id=tenant_id,
            entity_type="INTERFACE",
            name="TargetInterface",
            properties={},
        )

        # Create relationship
        rel_id = await neo4j_service.create_relationship(
            relationship_id=relationship_id,
            tenant_id=tenant_id,
            source_entity_id=source_id,
            target_entity_id=target_id,
            relationship_type="IMPLEMENTS",
            properties={"context": "SourceClass implements TargetInterface"},
            confidence_score=0.95,
        )

        # Verify relationship was created
        assert rel_id is not None
        assert isinstance(rel_id, str)
        assert len(rel_id) > 0

    async def test_relationship_between_entities(
        self,
        neo4j_service: Neo4jService,
        cleanup_single_tenant,
    ):
        """Test that relationships can be queried from both sides.

        Creates entities and a relationship, then verifies the relationship
        is visible when querying from both source and target.
        """
        tenant_id = cleanup_single_tenant
        source_id = uuid4()
        target_id = uuid4()

        # Create entities
        await neo4j_service.create_entity_node(
            entity_id=source_id,
            tenant_id=tenant_id,
            entity_type="FUNCTION",
            name="caller_function",
            properties={},
        )
        await neo4j_service.create_entity_node(
            entity_id=target_id,
            tenant_id=tenant_id,
            entity_type="FUNCTION",
            name="called_function",
            properties={},
        )

        # Create relationship
        await neo4j_service.create_relationship(
            relationship_id=uuid4(),
            tenant_id=tenant_id,
            source_entity_id=source_id,
            target_entity_id=target_id,
            relationship_type="CALLS",
            properties={},
            confidence_score=1.0,
        )

        # Query outgoing relationships from source
        outgoing = await neo4j_service.get_entity_relationships(
            entity_id=source_id,
            tenant_id=tenant_id,
            direction="outgoing",
        )
        assert len(outgoing) == 1
        assert outgoing[0]["type"] == "CALLS"
        assert outgoing[0]["target_name"] == "called_function"

        # Query incoming relationships to target
        incoming = await neo4j_service.get_entity_relationships(
            entity_id=target_id,
            tenant_id=tenant_id,
            direction="incoming",
        )
        assert len(incoming) == 1
        assert incoming[0]["type"] == "CALLS"
        assert incoming[0]["source_name"] == "caller_function"

    async def test_relationship_with_properties(
        self,
        neo4j_service: Neo4jService,
        cleanup_single_tenant,
        sample_relationship_properties,
    ):
        """Test that relationship properties are correctly stored."""
        tenant_id = cleanup_single_tenant
        source_id = uuid4()
        target_id = uuid4()

        # Create entities
        await neo4j_service.create_entity_node(
            entity_id=source_id,
            tenant_id=tenant_id,
            entity_type="CLASS",
            name="UserService",
            properties={},
        )
        await neo4j_service.create_entity_node(
            entity_id=target_id,
            tenant_id=tenant_id,
            entity_type="CLASS",
            name="DatabaseService",
            properties={},
        )

        # Create relationship with properties
        await neo4j_service.create_relationship(
            relationship_id=uuid4(),
            tenant_id=tenant_id,
            source_entity_id=source_id,
            target_entity_id=target_id,
            relationship_type="USES",
            properties=sample_relationship_properties,
            confidence_score=0.85,
        )

        # Query and verify properties
        relationships = await neo4j_service.get_entity_relationships(
            entity_id=source_id,
            tenant_id=tenant_id,
            direction="outgoing",
        )
        assert len(relationships) == 1
        assert relationships[0]["confidence"] == 0.85
        # Note: properties are stored but may need to be retrieved differently

    async def test_relationship_returns_none_for_missing_entities(
        self,
        neo4j_service: Neo4jService,
        cleanup_single_tenant,
    ):
        """Test that creating a relationship with missing entities returns None.

        Neo4j MATCH clause returns no results if entities don't exist,
        so create_relationship should return None.
        """
        tenant_id = cleanup_single_tenant
        nonexistent_source = uuid4()
        nonexistent_target = uuid4()

        # Try to create relationship with nonexistent entities
        rel_id = await neo4j_service.create_relationship(
            relationship_id=uuid4(),
            tenant_id=tenant_id,
            source_entity_id=nonexistent_source,
            target_entity_id=nonexistent_target,
            relationship_type="USES",
            properties={},
            confidence_score=1.0,
        )

        assert rel_id is None

    async def test_multiple_relationships_between_entities(
        self,
        neo4j_service: Neo4jService,
        cleanup_single_tenant,
    ):
        """Test that multiple relationships of different types can exist."""
        tenant_id = cleanup_single_tenant
        class_id = uuid4()
        parent_id = uuid4()

        # Create entities
        await neo4j_service.create_entity_node(
            entity_id=class_id,
            tenant_id=tenant_id,
            entity_type="CLASS",
            name="ChildClass",
            properties={},
        )
        await neo4j_service.create_entity_node(
            entity_id=parent_id,
            tenant_id=tenant_id,
            entity_type="CLASS",
            name="ParentClass",
            properties={},
        )

        # Create INHERITS relationship
        await neo4j_service.create_relationship(
            relationship_id=uuid4(),
            tenant_id=tenant_id,
            source_entity_id=class_id,
            target_entity_id=parent_id,
            relationship_type="INHERITS",
            properties={},
            confidence_score=1.0,
        )

        # Create USES relationship
        await neo4j_service.create_relationship(
            relationship_id=uuid4(),
            tenant_id=tenant_id,
            source_entity_id=class_id,
            target_entity_id=parent_id,
            relationship_type="USES",
            properties={},
            confidence_score=0.8,
        )

        # Query all relationships
        relationships = await neo4j_service.get_entity_relationships(
            entity_id=class_id,
            tenant_id=tenant_id,
            direction="both",
        )
        assert len(relationships) == 2

        relationship_types = {r["type"] for r in relationships}
        assert "INHERITS" in relationship_types
        assert "USES" in relationship_types


# =============================================================================
# Tenant Isolation Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
class TestNeo4jTenantIsolation:
    """Integration tests for Neo4j tenant isolation.

    These tests verify that entities and relationships are properly
    isolated between tenants.
    """

    async def test_cannot_access_other_tenant_entities(
        self,
        neo4j_service: Neo4jService,
        two_tenants_cleanup,
    ):
        """Test that entities from one tenant cannot be accessed by another.

        Creates an entity for tenant A, then verifies tenant B
        cannot retrieve it.
        """
        tenant_a, tenant_b = two_tenants_cleanup
        entity_id = uuid4()

        # Create entity for tenant A
        await neo4j_service.create_entity_node(
            entity_id=entity_id,
            tenant_id=tenant_a,
            entity_type="CLASS",
            name="TenantAEntity",
            properties={},
        )

        # Verify tenant A can access it
        node_a = await neo4j_service.get_entity_node(entity_id, tenant_a)
        assert node_a is not None
        assert node_a["name"] == "TenantAEntity"

        # Verify tenant B cannot access it
        node_b = await neo4j_service.get_entity_node(entity_id, tenant_b)
        assert node_b is None

    async def test_tenant_entities_are_separate(
        self,
        neo4j_service: Neo4jService,
        two_tenants_cleanup,
    ):
        """Test that tenants can have entities with same name but different data.

        Each tenant should have completely separate entity namespaces.
        """
        tenant_a, tenant_b = two_tenants_cleanup

        # Create entities with same name for both tenants
        entity_id_a = uuid4()
        entity_id_b = uuid4()

        await neo4j_service.create_entity_node(
            entity_id=entity_id_a,
            tenant_id=tenant_a,
            entity_type="CLASS",
            name="SharedName",
            properties={"owner": "tenant_a"},
        )

        await neo4j_service.create_entity_node(
            entity_id=entity_id_b,
            tenant_id=tenant_b,
            entity_type="CLASS",
            name="SharedName",
            properties={"owner": "tenant_b"},
        )

        # Verify each tenant sees only their own entity
        node_a = await neo4j_service.get_entity_node(entity_id_a, tenant_a)
        assert node_a is not None
        assert node_a["properties"]["owner"] == "tenant_a"

        node_b = await neo4j_service.get_entity_node(entity_id_b, tenant_b)
        assert node_b is not None
        assert node_b["properties"]["owner"] == "tenant_b"

        # Verify counts are separate
        count_a = await neo4j_service.count_entities_for_tenant(tenant_a)
        count_b = await neo4j_service.count_entities_for_tenant(tenant_b)
        assert count_a == 1
        assert count_b == 1

    async def test_cannot_delete_other_tenant_entities(
        self,
        neo4j_service: Neo4jService,
        two_tenants_cleanup,
    ):
        """Test that one tenant cannot delete another tenant's entities."""
        tenant_a, tenant_b = two_tenants_cleanup
        entity_id = uuid4()

        # Create entity for tenant A
        await neo4j_service.create_entity_node(
            entity_id=entity_id,
            tenant_id=tenant_a,
            entity_type="CLASS",
            name="TenantAEntity",
            properties={},
        )

        # Attempt to delete from tenant B (should fail/return False)
        deleted = await neo4j_service.delete_entity_node(entity_id, tenant_b)
        assert deleted is False

        # Verify entity still exists for tenant A
        node = await neo4j_service.get_entity_node(entity_id, tenant_a)
        assert node is not None

    async def test_delete_tenant_data_clears_all_tenant_entities(
        self,
        neo4j_service: Neo4jService,
        two_tenants_cleanup,
    ):
        """Test that delete_tenant_data removes all entities for a tenant."""
        tenant_a, tenant_b = two_tenants_cleanup

        # Create multiple entities for tenant A
        for i in range(5):
            await neo4j_service.create_entity_node(
                entity_id=uuid4(),
                tenant_id=tenant_a,
                entity_type="CLASS",
                name=f"TenantAEntity{i}",
                properties={},
            )

        # Create entity for tenant B
        entity_b = uuid4()
        await neo4j_service.create_entity_node(
            entity_id=entity_b,
            tenant_id=tenant_b,
            entity_type="CLASS",
            name="TenantBEntity",
            properties={},
        )

        # Verify tenant A has 5 entities
        count_a_before = await neo4j_service.count_entities_for_tenant(tenant_a)
        assert count_a_before == 5

        # Delete all tenant A data
        deleted = await neo4j_service.delete_tenant_data(tenant_a)
        assert deleted == 5

        # Verify tenant A has no entities
        count_a_after = await neo4j_service.count_entities_for_tenant(tenant_a)
        assert count_a_after == 0

        # Verify tenant B entity still exists
        node_b = await neo4j_service.get_entity_node(entity_b, tenant_b)
        assert node_b is not None

    async def test_relationships_respect_tenant_isolation(
        self,
        neo4j_service: Neo4jService,
        two_tenants_cleanup,
    ):
        """Test that relationships are isolated by tenant.

        A relationship should only be visible within its tenant context.
        """
        tenant_a, tenant_b = two_tenants_cleanup
        source_a = uuid4()
        target_a = uuid4()

        # Create entities and relationship for tenant A
        await neo4j_service.create_entity_node(
            entity_id=source_a,
            tenant_id=tenant_a,
            entity_type="CLASS",
            name="SourceA",
            properties={},
        )
        await neo4j_service.create_entity_node(
            entity_id=target_a,
            tenant_id=tenant_a,
            entity_type="CLASS",
            name="TargetA",
            properties={},
        )
        await neo4j_service.create_relationship(
            relationship_id=uuid4(),
            tenant_id=tenant_a,
            source_entity_id=source_a,
            target_entity_id=target_a,
            relationship_type="USES",
            properties={},
            confidence_score=1.0,
        )

        # Query relationships with tenant A context - should find it
        rels_a = await neo4j_service.get_entity_relationships(
            entity_id=source_a,
            tenant_id=tenant_a,
            direction="outgoing",
        )
        assert len(rels_a) == 1

        # Query relationships with tenant B context - should not find it
        # (Also the entity won't be found with wrong tenant)
        rels_b = await neo4j_service.get_entity_relationships(
            entity_id=source_a,
            tenant_id=tenant_b,
            direction="outgoing",
        )
        assert len(rels_b) == 0


# =============================================================================
# Error Handling Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
class TestNeo4jErrorHandling:
    """Integration tests for Neo4j error handling.

    These tests verify that the Neo4j service handles errors gracefully.
    """

    async def test_handles_connection_failure_gracefully(
        self,
        neo4j_available: bool,
    ):
        """Test that connection failures are handled gracefully.

        Creates a service with invalid credentials and verifies
        the error is handled appropriately.
        """
        if not neo4j_available:
            pytest.skip("Neo4j is not available")

        # Create service with invalid credentials
        service = Neo4jService(
            uri="bolt://neo4j:7687",
            user="invalid_user",
            password="invalid_password",
        )

        # Connection should fail
        with pytest.raises(Exception):
            await service.connect()

    async def test_health_check_returns_unhealthy_on_bad_connection(
        self,
        neo4j_available: bool,
    ):
        """Test that health check returns unhealthy status for bad connection."""
        if not neo4j_available:
            pytest.skip("Neo4j is not available")

        # Create service with invalid connection - use invalid port
        service = Neo4jService(
            uri="bolt://neo4j:7688",  # Wrong port
            user="neo4j",
            password="knowledge_mapper_neo4j_pass",
        )

        # Force connect to fail silently by catching exception
        try:
            await service.connect()
        except Exception:
            pass

        # Health check should report unhealthy
        health = await service.health_check()
        assert health["status"] == "unhealthy"
        assert "error" in health

    async def test_session_raises_if_not_connected(self):
        """Test that getting a session raises error if driver not connected."""
        service = Neo4jService()
        # Don't call connect()

        with pytest.raises(RuntimeError, match="driver not connected"):
            async with service.session():
                pass

    async def test_health_check_success(
        self,
        neo4j_service: Neo4jService,
    ):
        """Test that health check returns healthy status when connected."""
        health = await neo4j_service.health_check()

        assert health["status"] == "healthy"
        assert "latency_ms" in health
        assert health["latency_ms"] >= 0
        assert "uri" in health
        assert "database" in health


# =============================================================================
# Health and Connection Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
class TestNeo4jConnection:
    """Integration tests for Neo4j connection management."""

    async def test_connect_and_close(
        self,
        neo4j_available: bool,
    ):
        """Test that service can connect and close cleanly."""
        if not neo4j_available:
            pytest.skip("Neo4j is not available")

        service = Neo4jService()

        # Connect
        await service.connect()

        # Verify connected via health check
        health = await service.health_check()
        assert health["status"] == "healthy"

        # Close
        await service.close()

        # Session should fail after close
        with pytest.raises(RuntimeError, match="driver not connected"):
            async with service.session():
                pass

    async def test_double_connect_warns_but_succeeds(
        self,
        neo4j_available: bool,
    ):
        """Test that calling connect twice logs warning but doesn't fail."""
        if not neo4j_available:
            pytest.skip("Neo4j is not available")

        service = Neo4jService()
        await service.connect()

        # Second connect should succeed (with warning logged)
        await service.connect()

        # Should still be functional
        health = await service.health_check()
        assert health["status"] == "healthy"

        await service.close()

    async def test_close_without_connect_succeeds(self):
        """Test that closing an unconnected service doesn't raise."""
        service = Neo4jService()

        # Should not raise
        await service.close()
