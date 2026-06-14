"""Custom exception hierarchy for Project TUTORIAL."""


class TutorialException(Exception):
    """Base exception for all tutorial-domain errors."""


class AgentException(TutorialException):
    """Errors raised by autonomous agents."""


class AgentStartupError(AgentException):
    """Agent failed during initialization or startup."""


class AgentRuntimeError(AgentException):
    """Agent failed while executing its main loop."""


class AgentCommunicationError(AgentException):
    """Agent-to-agent messaging failures."""


class AgentTimeoutError(AgentException):
    """Agent coordination timed out."""


class IncidentException(TutorialException):
    """Errors related to incident handling."""


class InvalidIncidentError(IncidentException):
    """Incident payload or metadata is inconsistent."""


class InvestigationError(IncidentException):
    """Investigation workflow failed."""


class LessonException(TutorialException):
    """Errors in teaching or lesson synthesis."""


class LessonGenerationError(LessonException):
    """Lesson content could not be produced."""


class CurriculumMappingError(LessonException):
    """Mapping to standards or curriculum failed."""


class IntegrationException(TutorialException):
    """Errors when integrating with external systems."""


class SIFTConnectionError(IntegrationException):
    """SIFT workstation connectivity failure."""


class SplunkAPIError(IntegrationException):
    """Splunk REST or SDK failure."""


class MCPConnectionError(IntegrationException):
    """MCP server connectivity failure."""


class UiPathAPIError(IntegrationException):
    """UiPath orchestrator API failure."""


class ConfigurationError(TutorialException):
    """Invalid or incomplete configuration."""
