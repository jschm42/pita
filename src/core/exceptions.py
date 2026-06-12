"""Custom exceptions for the pita Agentic QA system.

This module contains clean, specific exception classes to handle domain-level,
browser-automation, and LLM-interaction errors.
"""


class PitaError(Exception):
    """Base exception class for all errors in the pita application."""

    pass


class BrowserServiceError(PitaError):
    """Base exception for issues within the Playwright Browser Service."""

    pass


class NavigationError(BrowserServiceError):
    """Raised when navigation to a URL fails or times out."""

    pass


class ActionExecutionError(BrowserServiceError):
    """Raised when performing a browser action (click, type, select) fails."""

    pass


class LLMClientError(PitaError):
    """Base exception for failures in communicating with the LLM API."""

    pass


class LLMResponseParseError(LLMClientError):
    """Raised when the LLM response does not conform to the expected schema."""

    pass


class AgentError(PitaError):
    """Base exception for high-level agent orchestrator errors."""

    pass
