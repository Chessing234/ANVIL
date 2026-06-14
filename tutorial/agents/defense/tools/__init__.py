"""Defense forensic and IR tool adapters."""

from agents.defense.tools.chain_of_custody import CustodyChain
from agents.defense.tools.containment_tools import (
    AccountManager,
    DNSSinkholer,
    FileQuarantiner,
    HostIsolator,
    IPBlocker,
    ProcessTerminator,
    ToolExecutionResult,
)
from agents.defense.tools.evidence_storage import EvidenceVault
from agents.defense.tools.ioc_matcher import IOCMatcher
from agents.defense.tools.log_analyzer import EventCorrelation, LogAnalyzer, LogEntry
from agents.defense.tools.memory_analyzer import MemoryAnalyzer, MemoryForensicsReport
from agents.defense.tools.network_analyzer import NetworkAnalysisResult, NetworkAnalyzer
from shared.models import IOCMatch

__all__ = [
    "AccountManager",
    "CustodyChain",
    "DNSSinkholer",
    "EventCorrelation",
    "EvidenceVault",
    "FileQuarantiner",
    "HostIsolator",
    "IOCMatch",
    "IOCMatcher",
    "IPBlocker",
    "LogAnalyzer",
    "LogEntry",
    "MemoryAnalyzer",
    "MemoryForensicsReport",
    "NetworkAnalysisResult",
    "NetworkAnalyzer",
    "ProcessTerminator",
    "ToolExecutionResult",
]
