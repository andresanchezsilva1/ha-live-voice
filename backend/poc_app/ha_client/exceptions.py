"""
Home Assistant Client Exceptions

Custom exception classes for Home Assistant client operations.
"""

import logging
from enum import Enum
from typing import Dict, Any, Optional


logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class HAClientError(Exception):
    """
    Base exception class for Home Assistant client errors
    """
    
    def __init__(
        self, 
        message: str, 
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        details: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None
    ):
        super().__init__(message)
        self.message = message
        self.severity = severity
        self.details = details or {}
        self.original_exception = original_exception
        self._log_error()
    
    def _log_error(self):
        """Log the error based on severity"""
        log_message = f"{self.__class__.__name__}: {self.message}"
        if self.details:
            log_message += f" - Details: {self.details}"
        
        if self.severity == ErrorSeverity.LOW:
            logger.debug(log_message)
        elif self.severity == ErrorSeverity.MEDIUM:
            logger.warning(log_message)
        elif self.severity == ErrorSeverity.HIGH:
            logger.error(log_message)
        elif self.severity == ErrorSeverity.CRITICAL:
            logger.critical(log_message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for serialization"""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "severity": self.severity.value,
            "details": self.details
        }


class HAConnectionError(HAClientError):
    """Raised when connection to Home Assistant fails"""
    
    def __init__(self, message: str = "Failed to connect to Home Assistant", **kwargs):
        super().__init__(message, severity=ErrorSeverity.HIGH, **kwargs)


class HAAuthenticationError(HAClientError):
    """Raised when authentication with Home Assistant fails"""
    
    def __init__(self, message: str = "Authentication failed", **kwargs):
        super().__init__(message, severity=ErrorSeverity.CRITICAL, **kwargs)


class HAAPIError(HAClientError):
    """Raised when Home Assistant API returns an error"""
    
    def __init__(self, message: str, status_code: Optional[int] = None, **kwargs):
        details = kwargs.pop('details', {})
        if status_code:
            details['status_code'] = status_code
        super().__init__(message, details=details, **kwargs)


class HAEntityNotFoundError(HAClientError):
    """Raised when a requested entity is not found"""
    
    def __init__(self, entity_id: str, **kwargs):
        message = f"Entity '{entity_id}' not found"
        details = kwargs.pop('details', {})
        details['entity_id'] = entity_id
        super().__init__(message, severity=ErrorSeverity.MEDIUM, details=details, **kwargs)


class HAServiceCallError(HAClientError):
    """Raised when a service call fails"""
    
    def __init__(self, domain: str, service: str, **kwargs):
        message = f"Service call failed: {domain}.{service}"
        details = kwargs.pop('details', {})
        details.update({'domain': domain, 'service': service})
        super().__init__(message, details=details, **kwargs)


class HATimeoutError(HAClientError):
    """Raised when a request times out"""
    
    def __init__(self, message: str = "Request timed out", **kwargs):
        super().__init__(message, severity=ErrorSeverity.HIGH, **kwargs)


class HAValidationError(HAClientError):
    """Raised when input validation fails"""
    
    def __init__(self, message: str, field: Optional[str] = None, **kwargs):
        details = kwargs.pop('details', {})
        if field:
            details['field'] = field
        super().__init__(message, severity=ErrorSeverity.LOW, details=details, **kwargs)


class HAConfigurationError(HAClientError):
    """Raised when there's a configuration issue"""
    
    def __init__(self, message: str = "Configuration error", **kwargs):
        super().__init__(message, severity=ErrorSeverity.CRITICAL, **kwargs)


class HARateLimitError(HAClientError):
    """Raised when rate limit is exceeded"""
    
    def __init__(self, message: str = "Rate limit exceeded", retry_after: Optional[int] = None, **kwargs):
        details = kwargs.pop('details', {})
        if retry_after:
            details['retry_after'] = retry_after
        super().__init__(message, severity=ErrorSeverity.MEDIUM, details=details, **kwargs)


def create_ha_error_from_response(response, original_exception: Optional[Exception] = None) -> HAClientError:
    """
    Create appropriate HAClientError from HTTP response
    
    Args:
        response: HTTP response object
        original_exception: Original exception that caused this error
        
    Returns:
        Appropriate HAClientError subclass
    """
    status_code = getattr(response, 'status_code', None)
    
    try:
        error_data = response.json() if hasattr(response, 'json') else {}
    except:
        error_data = {}
    
    message = error_data.get('message', f"HTTP {status_code} error")
    
    if status_code == 401:
        return HAAuthenticationError(message, original_exception=original_exception)
    elif status_code == 404:
        return HAEntityNotFoundError(
            error_data.get('entity_id', 'unknown'), 
            original_exception=original_exception
        )
    elif status_code == 429:
        retry_after = error_data.get('retry_after')
        return HARateLimitError(message, retry_after=retry_after, original_exception=original_exception)
    elif status_code >= 500:
        return HAAPIError(
            message, 
            status_code=status_code, 
            severity=ErrorSeverity.HIGH,
            original_exception=original_exception
        )
    else:
        return HAAPIError(
            message, 
            status_code=status_code,
            original_exception=original_exception
        ) 