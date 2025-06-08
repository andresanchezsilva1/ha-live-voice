"""
Módulo cliente Gemini Live para integração com Home Assistant
"""

# Importar do gemini_live_api_client.py que tem a implementação oficial da Live API
from .gemini_live_api_client import GeminiLiveAPIClient as GeminiLiveClient
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
