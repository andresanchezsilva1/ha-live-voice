"""
Custom exceptions for the POC application.
"""


class BaseAppError(Exception):
    """Base exception class for the application"""
    pass


class SessionNotFoundError(BaseAppError):
    """Raised when a session is not found"""
    pass


class SessionCreationError(BaseAppError):
    """Raised when session creation fails"""
    pass


class AudioProcessingError(BaseAppError):
    """Raised when audio processing fails"""
    pass


class HomeAssistantError(BaseAppError):
    """Raised when Home Assistant operations fail"""
    pass


class IntegrationError(BaseAppError):
    """Raised when integration components fail"""
    pass


 