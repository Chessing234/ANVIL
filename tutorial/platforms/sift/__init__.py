"""SANS SIFT Workstation integration for FIND EVIL! investigations."""

from platforms.sift.accuracy_report import AccuracyReport, AccuracyReportGenerator
from platforms.sift.connector import (
    CommandResult,
    FileEntry,
    SIFTConnector,
    SIFTSystemInfo,
)
from platforms.sift.execution_engine import SIFTExecutionEngine
from platforms.sift.playbook_runner import Playbook, PlaybookResult, PlaybookRunner
from platforms.sift.self_correction import (
    CorrectionStrategy,
    FindEvilCorrectionEvent,
    SelfCorrectingInvestigator,
)

__all__ = [
    "AccuracyReport",
    "AccuracyReportGenerator",
    "CommandResult",
    "CorrectionStrategy",
    "FileEntry",
    "FindEvilCorrectionEvent",
    "Playbook",
    "PlaybookResult",
    "PlaybookRunner",
    "SIFTConnector",
    "SIFTExecutionEngine",
    "SIFTSystemInfo",
    "SelfCorrectingInvestigator",
]
