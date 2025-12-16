"""
Modular text preprocessing and chunking for entity extraction.

This module provides:
- Preprocessors: Clean and extract main content from HTML/text
- Chunkers: Split documents into smaller pieces for processing
- Entity Mergers: Combine entities from multiple chunks

Example:
    from app.preprocessing import PreprocessingPipeline, PipelineConfig

    config = PipelineConfig(chunk_size=3000, chunk_overlap=200)
    pipeline = PreprocessingPipeline(config)
    result = await pipeline.process(content=html, extractor=extractor, url=url)
"""

from app.preprocessing.base import Chunker, EntityMerger, Preprocessor
from app.preprocessing.exceptions import (
    ChunkerError,
    ChunkerNotRegisteredError,
    EntityMergerError,
    EntityMergerNotRegisteredError,
    PreprocessingError,
    PreprocessorError,
    PreprocessorNotRegisteredError,
)
from app.preprocessing.factory import (
    ChunkerFactory,
    ChunkerType,
    EntityMergerFactory,
    EntityMergerType,
    PreprocessorFactory,
    PreprocessorType,
)
from app.preprocessing.schemas import (
    Chunk,
    ChunkingResult,
    EntityMergeCandidate,
    EntityMergeDecision,
    PreprocessingResult,
)

# Import implementations to trigger factory registration
# These must be imported AFTER the factories are defined
from app.preprocessing import chunkers  # noqa: E402, F401
from app.preprocessing import mergers  # noqa: E402, F401
from app.preprocessing import preprocessors  # noqa: E402, F401

# Import pipeline after all factories are populated
from app.preprocessing.pipeline import PipelineConfig, PipelineResult, PreprocessingPipeline

__all__ = [
    # Protocols
    "Preprocessor",
    "Chunker",
    "EntityMerger",
    # Factories
    "PreprocessorFactory",
    "ChunkerFactory",
    "EntityMergerFactory",
    # Types
    "PreprocessorType",
    "ChunkerType",
    "EntityMergerType",
    # Schemas
    "PreprocessingResult",
    "Chunk",
    "ChunkingResult",
    "EntityMergeCandidate",
    "EntityMergeDecision",
    # Pipeline
    "PreprocessingPipeline",
    "PipelineConfig",
    "PipelineResult",
    # Exceptions
    "PreprocessingError",
    "PreprocessorError",
    "PreprocessorNotRegisteredError",
    "ChunkerError",
    "ChunkerNotRegisteredError",
    "EntityMergerError",
    "EntityMergerNotRegisteredError",
]
