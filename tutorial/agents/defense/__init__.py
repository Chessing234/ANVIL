"""Defense investigation and forensic subsystems."""

from agents.defense.analysis_strategies import (
    FileSystemAnalysisStrategy,
    IOCMatchingStrategy,
    LogCorrelationStrategy,
    MemoryAnalysisStrategy,
    NetworkAnalysisStrategy,
    StrategySelector,
)
from agents.defense.containment import ContainmentAgent, ContainmentExecutor
from agents.defense.evidence_collection import EvidenceCollectionAgent
from agents.defense.hypothesis_manager import HypothesisManager
from agents.defense.investigation import InvestigationAgent
from agents.defense.reasoning_engine import ReasoningEngine
from agents.defense.remediation import RemediationAgent, RemediationPlanner

__all__ = [
    "ContainmentAgent",
    "ContainmentExecutor",
    "EvidenceCollectionAgent",
    "FileSystemAnalysisStrategy",
    "HypothesisManager",
    "IOCMatchingStrategy",
    "InvestigationAgent",
    "LogCorrelationStrategy",
    "MemoryAnalysisStrategy",
    "NetworkAnalysisStrategy",
    "ReasoningEngine",
    "RemediationAgent",
    "RemediationPlanner",
    "StrategySelector",
]
