"""
End-to-end tests for the Knowledge Mapper extraction pipeline.

This package contains E2E tests that verify the complete flow from
page scraping through entity extraction to Neo4j synchronization.

Test Categories:
- Full Pipeline Tests: Complete flow from page -> extraction -> graph
- Extraction Trigger Tests: PageScraped -> ExtractionProcess creation
- Worker Tests: ExtractionProcess -> Entity extraction
- Neo4j Sync Tests: Entity -> Neo4j graph sync

Requirements:
- PostgreSQL database with test data
- Neo4j graph database (optional, tests skip if unavailable)
- Ollama service (optional, tests skip if unavailable)

Run with: pytest -m e2e tests/e2e/
"""
