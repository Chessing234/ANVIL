"""Knowledge flywheel package (lazy-loads engine to avoid import cycles)."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

from knowledge.concept_extractor import ConceptExtractor
from knowledge.embedding.embedder import ConceptEmbedder
from knowledge.embedding.similarity import SimilaritySearch
from knowledge.feedback_loops import FeedbackAggregator, FeedbackCollector
from knowledge.knowledge_graph import KnowledgeGraph
from knowledge.models import (
    ConceptEdge,
    ConceptNode,
    DefenseFeedback,
    DefenseInsight,
    FeedbackReport,
    GraphStats,
    LearningSignal,
    StudentProgress,
)

if TYPE_CHECKING:
    from knowledge.flywheel_engine import FlywheelEngine

__all__ = [
    "ConceptEdge",
    "ConceptEmbedder",
    "ConceptExtractor",
    "ConceptNode",
    "DefenseFeedback",
    "DefenseInsight",
    "FeedbackAggregator",
    "FeedbackCollector",
    "FeedbackReport",
    "FlywheelEngine",
    "GraphStats",
    "KnowledgeGraph",
    "LearningSignal",
    "SimilaritySearch",
    "StudentProgress",
]


def __getattr__(name: str) -> Any:
    if name == "FlywheelEngine":
        mod = importlib.import_module("knowledge.flywheel_engine")
        return mod.FlywheelEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
