"""
Home Assistant Client Package

This package provides a client for communicating with Home Assistant REST API
with robust error handling, retry logic, and Pydantic input validation.
"""

from .client import HomeAssistantClient, HAEntityState, HAServiceCall
from .config import HAClientConfig, ConfigManager
from .exceptions import (
    HAClientError,
    HAConnectionError,
    HAAuthenticationError,
    HAAPIError,
    HAEntityNotFoundError,
    HAServiceCallError,
    HATimeoutError,
    HAValidationError,
    HAConfigurationError,
    HARateLimitError,
    ErrorSeverity,
    create_ha_error_from_response
)
from .retry_logic import (
    RetryConfig,
    CircuitBreakerConfig,
    RetryManager,
    with_retry,
    DEFAULT_RETRY_MANAGER
)
from .models import (
    # Base models
    EntityIdModel,
    StateModel,
    ColorModel,
    ServiceCallModel,
    
    # Device control models
    LightControlModel,
    SwitchControlModel,
    ClimateControlModel,
    MediaPlayerControlModel,
    CoverControlModel,
    FanControlModel,
    SceneControlModel,
    ScriptControlModel,
    AutomationControlModel,
    
    # Input models
    InputBooleanModel,
    InputNumberModel,
    InputSelectModel,
    InputTextModel,
    InputDateTimeModel,
    
    # Batch operation models
    BatchEntityOperation,
    BatchServiceCall,
    
    # Enums
    HVACMode,
    MediaPlayerAction,
    CoverAction,
    AutomationAction
)

__all__ = [
    # Client classes
    "HomeAssistantClient",
    "HAEntityState", 
    "HAServiceCall",
    
    # Configuration classes
    "HAClientConfig",
    "ConfigManager",
    
    # Exception classes
    "HAClientError",
    "HAConnectionError",
    "HAAuthenticationError",
    "HAAPIError",
    "HAEntityNotFoundError",
    "HAServiceCallError",
    "HATimeoutError",
    "HAValidationError",
    "HAConfigurationError",
    "HARateLimitError",
    "ErrorSeverity",
    "create_ha_error_from_response",
    
    # Retry logic classes
    "RetryConfig",
    "CircuitBreakerConfig",
    "RetryManager",
    "with_retry",
    "DEFAULT_RETRY_MANAGER",
    
    # Validation models - Base
    "EntityIdModel",
    "StateModel",
    "ColorModel",
    "ServiceCallModel",
    
    # Validation models - Device control
    "LightControlModel",
    "SwitchControlModel",
    "ClimateControlModel",
    "MediaPlayerControlModel",
    "CoverControlModel",
    "FanControlModel",
    "SceneControlModel",
    "ScriptControlModel",
    "AutomationControlModel",
    
    # Validation models - Input
    "InputBooleanModel",
    "InputNumberModel",
    "InputSelectModel",
    "InputTextModel",
    "InputDateTimeModel",
    
    # Validation models - Batch
    "BatchEntityOperation",
    "BatchServiceCall",
    
    # Enums
    "HVACMode",
    "MediaPlayerAction",
    "CoverAction",
    "AutomationAction"
]
