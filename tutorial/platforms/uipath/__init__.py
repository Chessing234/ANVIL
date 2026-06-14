"""UiPath Maestro / Orchestrator integration for AgentHack (Track 1: Maestro Case)."""

from platforms.uipath.agent_bridge import AgentBridge
from platforms.uipath.attended_automation import AttendedAutomation, ContainmentAction
from platforms.uipath.maestro_orchestrator import (
    JobStatus,
    MaestroOrchestrator,
    ProcessInfo,
    QueueItem,
    RobotInfo,
)
from platforms.uipath.unattended_runner import UnattendedRunner
from platforms.uipath.workflow_generator import WorkflowDefinition, WorkflowGenerator

__all__ = [
    "AgentBridge",
    "AttendedAutomation",
    "ContainmentAction",
    "JobStatus",
    "MaestroOrchestrator",
    "ProcessInfo",
    "QueueItem",
    "RobotInfo",
    "UnattendedRunner",
    "WorkflowDefinition",
    "WorkflowGenerator",
]
