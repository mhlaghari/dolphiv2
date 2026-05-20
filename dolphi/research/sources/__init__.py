from .base import ResearchDocument, ResearchSource, dedupe_documents
from .brave import BraveResearchSource
from .registry import ResearchSourceRegistry, build_source_registry
from .searxng import SearXNGResearchSource
from .static import StaticResearchSource

__all__ = [
    "ResearchDocument",
    "ResearchSource",
    "ResearchSourceRegistry",
    "BraveResearchSource",
    "SearXNGResearchSource",
    "StaticResearchSource",
    "build_source_registry",
    "dedupe_documents",
]
