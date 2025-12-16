"""
Integration tests for entity consolidation services.

This package contains integration tests for:
- BlockingEngine: Candidate generation using database indexes
- StringSimilarityService: String-based similarity computation
- Full consolidation pipeline: Blocking -> Similarity -> Decision

These tests require a running PostgreSQL database with the
pg_trgm and fuzzystrmatch extensions enabled.
"""
