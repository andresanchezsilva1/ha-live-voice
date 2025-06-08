"""
Módulo cliente Gemini Live para integração com Home Assistant
"""

from .client import GeminiLiveClient
from .function_handler import HomeAssistantFunctionHandler
from .ha_functions import (
    HA_FUNCTION_DECLARATIONS,
    FUNCTION_DOMAINS,
    get_functions_for_domain,
    get_all_function_names,
    get_function_by_name
)

__all__ = [
    "GeminiLiveClient",
    "HomeAssistantFunctionHandler", 
    "HA_FUNCTION_DECLARATIONS",
    "FUNCTION_DOMAINS",
    "get_functions_for_domain",
    "get_all_function_names",
    "get_function_by_name"
]
