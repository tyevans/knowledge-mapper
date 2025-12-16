"""
Preprocessor implementations for content extraction.

This module provides concrete implementations of the Preprocessor protocol:
- TrafilaturaPreprocessor: Uses trafilatura for robust HTML content extraction
- PassthroughPreprocessor: Returns content as-is (for plain text or testing)

Preprocessors are registered via decorators and created via PreprocessorFactory.
"""

# Import implementations to trigger registration
from app.preprocessing.preprocessors.passthrough_preprocessor import PassthroughPreprocessor
from app.preprocessing.preprocessors.trafilatura_preprocessor import TrafilaturaPreprocessor

__all__ = [
    "TrafilaturaPreprocessor",
    "PassthroughPreprocessor",
]
