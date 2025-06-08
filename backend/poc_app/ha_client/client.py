"""
Home Assistant Client Module

This module provides a client for communicating with Home Assistant REST API
to control devices and retrieve information.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from urllib.parse import urljoin

import httpx
from pydantic import BaseModel, Field, validator, ValidationError

from .exceptions import (
    HAClientError,
    HAConnectionError,
    HAAuthenticationError,
    HAAPIError,
    HAEntityNotFoundError,
    HATimeoutError,
    HAConfigurationError,
    HAValidationError,
    create_ha_error_from_response
)
from .retry_logic import (
    RetryManager,
    RetryConfig,
    CircuitBreakerConfig,
    DEFAULT_RETRY_MANAGER
)
from .models import (
    LightControlModel, SwitchControlModel, ClimateControlModel, 
    MediaPlayerControlModel, CoverControlModel, FanControlModel,
    SceneControlModel, ScriptControlModel, AutomationControlModel,
    InputBooleanModel, InputNumberModel, InputSelectModel, 
    InputTextModel, InputDateTimeModel, ServiceCallModel,
    EntityIdModel, BatchEntityOperation, BatchServiceCall
)

from .config import HAClientConfig, ConfigManager


logger = logging.getLogger(__name__)


def _validate_input(model_class, **kwargs):
    """
    Validate input parameters using Pydantic model
    
    Args:
        model_class: Pydantic model class to use for validation
        **kwargs: Parameters to validate
        
    Returns:
        Validated model instance
        
    Raises:
        HAValidationError: If validation fails
    """
    try:
        return model_class(**kwargs)
    except ValidationError as e:
        error_details = []
        for error in e.errors():
            field = ".".join(str(x) for x in error["loc"])
            message = error["msg"]
            error_details.append(f"{field}: {message}")
        
        raise HAValidationError(
            f"Input validation failed: {'; '.join(error_details)}",
            original_exception=e
        )


class HAEntityState(BaseModel):
    """Model for Home Assistant entity state"""
    entity_id: str
    state: str
    attributes: Dict[str, Any] = Field(default_factory=dict)
    last_changed: Optional[str] = None
    last_updated: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class HAServiceCall(BaseModel):
    """Model for Home Assistant service call"""
    domain: str
    service: str
    service_data: Dict[str, Any] = Field(default_factory=dict)
    target: Optional[Dict[str, Any]] = None


class HomeAssistantClient:
    """
    Client for communicating with Home Assistant REST API with robust error handling and retry logic
    """
    
    def __init__(
        self, 
        base_url: str, 
        access_token: str, 
        timeout: float = 10.0,
        retry_config: Optional[RetryConfig] = None,
        circuit_config: Optional[CircuitBreakerConfig] = None,
        use_global_retry_manager: bool = True
    ):
        """
        Initialize the Home Assistant client
        
        Args:
            base_url: Base URL of the Home Assistant instance (e.g., "http://homeassistant.local:8123")
            access_token: Long-lived access token for authentication
            timeout: Request timeout in seconds
            retry_config: Custom retry configuration
            circuit_config: Custom circuit breaker configuration
            use_global_retry_manager: Whether to use the global retry manager or create a new one
        """
        # Validate inputs
        if not base_url:
            raise HAConfigurationError("Base URL is required")
        if not access_token:
            raise HAConfigurationError("Access token is required")
        
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # Initialize HTTP client
        self.client = httpx.AsyncClient(
            headers=self.headers, 
            timeout=timeout,
            base_url=self.base_url
        )
        
        # Initialize retry manager
        if use_global_retry_manager:
            self.retry_manager = DEFAULT_RETRY_MANAGER
        else:
            retry_cfg = retry_config or RetryConfig()
            circuit_cfg = circuit_config or CircuitBreakerConfig()
            self.retry_manager = RetryManager(retry_cfg, circuit_cfg)
        
        logger.info(f"HomeAssistantClient initialized for {self.base_url}")
    
    @classmethod
    def from_env(cls, prefix: str = 'HA_') -> 'HomeAssistantClient':
        """
        Create HomeAssistantClient from environment variables
        
        Args:
            prefix: Environment variable prefix (default: 'HA_')
            
        Returns:
            HomeAssistantClient: Configured client instance
            
        Raises:
            HAConfigurationError: If required environment variables are missing
        """
        try:
            config_manager = ConfigManager()
            config = config_manager.load_from_env(prefix)
            
            return cls(
                base_url=config.base_url,
                access_token=config.access_token,
                timeout=config.timeout,
                retry_config=RetryConfig(
                    max_attempts=config.max_retries,
                    base_delay=config.retry_delay
                ),
                circuit_config=CircuitBreakerConfig(
                    failure_threshold=config.circuit_breaker_threshold,
                    recovery_timeout=config.circuit_breaker_timeout
                ),
                use_global_retry_manager=False
            )
        except Exception as e:
            raise HAConfigurationError(f"Failed to create client from environment: {str(e)}", original_exception=e)
    
    @classmethod
    def from_config_file(cls, config_path: Optional[Union[str, Path]] = None) -> 'HomeAssistantClient':
        """
        Create HomeAssistantClient from configuration file
        
        Args:
            config_path: Path to configuration file. If None, searches default paths.
            
        Returns:
            HomeAssistantClient: Configured client instance
            
        Raises:
            HAConfigurationError: If configuration file is not found or invalid
        """
        try:
            config_manager = ConfigManager(config_path)
            config = config_manager.load_from_file()
            
            return cls(
                base_url=config.base_url,
                access_token=config.access_token,
                timeout=config.timeout,
                retry_config=RetryConfig(
                    max_attempts=config.max_retries,
                    base_delay=config.retry_delay
                ),
                circuit_config=CircuitBreakerConfig(
                    failure_threshold=config.circuit_breaker_threshold,
                    recovery_timeout=config.circuit_breaker_timeout
                ),
                use_global_retry_manager=False
            )
        except Exception as e:
            raise HAConfigurationError(f"Failed to create client from config file: {str(e)}", original_exception=e)
    
    @classmethod
    def from_config(cls, config: HAClientConfig) -> 'HomeAssistantClient':
        """
        Create HomeAssistantClient from HAClientConfig object
        
        Args:
            config: Configuration object
            
        Returns:
            HomeAssistantClient: Configured client instance
        """
        return cls(
            base_url=config.base_url,
            access_token=config.access_token,
            timeout=config.timeout,
            retry_config=RetryConfig(
                max_attempts=config.max_retries,
                base_delay=config.retry_delay
            ),
            circuit_config=CircuitBreakerConfig(
                failure_threshold=config.circuit_breaker_threshold,
                recovery_timeout=config.circuit_breaker_timeout
            ),
            use_global_retry_manager=False
        )
    
    def get_config(self) -> HAClientConfig:
        """
        Get current client configuration as HAClientConfig object
        
        Returns:
            HAClientConfig: Current configuration
        """
        return HAClientConfig(
            base_url=self.base_url,
            access_token=self.headers["Authorization"].replace("Bearer ", ""),
            timeout=self.timeout,
            max_retries=getattr(self.retry_manager.retry_config, 'max_attempts', 3),
            retry_delay=getattr(self.retry_manager.retry_config, 'base_delay', 1.0),
            circuit_breaker_threshold=getattr(self.retry_manager.circuit_breaker.config, 'failure_threshold', 5),
            circuit_breaker_timeout=getattr(self.retry_manager.circuit_breaker.config, 'recovery_timeout', 60.0)
        )
    
    def update_config(self, **kwargs) -> None:
        """
        Update client configuration
        
        Args:
            **kwargs: Configuration fields to update
        """
        current_config = self.get_config()
        
        # Create updated configuration
        config_data = current_config.to_dict()
        config_data.update(kwargs)
        updated_config = HAClientConfig.from_dict(config_data)
        
        # Apply updates
        if 'base_url' in kwargs:
            self.base_url = updated_config.base_url
            self.client.base_url = self.base_url
        
        if 'access_token' in kwargs:
            self.headers["Authorization"] = f"Bearer {updated_config.access_token}"
            # Update client headers
            self.client.headers.update(self.headers)
        
        if 'timeout' in kwargs:
            self.timeout = updated_config.timeout
            # Note: httpx.AsyncClient timeout cannot be updated after creation
            # Client would need to be recreated for timeout changes
        
        logger.info(f"Client configuration updated: {list(kwargs.keys())}")
        
    async def __aenter__(self):
        """Async context manager entry"""
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
        
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()
    
    async def get_entity_state(self, entity_id: str) -> HAEntityState:
        """
        Get the current state of an entity
        
        Args:
            entity_id: The entity ID (e.g., "light.living_room")
            
        Returns:
            HAEntityState object with entity information
            
        Raises:
            HAClientError: If the request fails after retries
            HAValidationError: If entity_id format is invalid
        """
        # Validate entity ID format
        validated = _validate_input(EntityIdModel, entity_id=entity_id)
        
        async def _get_state():
            try:
                logger.debug(f"Getting state for entity: {validated.entity_id}")
                response = await self.client.get(f"/api/states/{validated.entity_id}")
                response.raise_for_status()
                data = response.json()
                return HAEntityState(**data)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    raise HAEntityNotFoundError(validated.entity_id, original_exception=e)
                raise create_ha_error_from_response(e.response, e)
            except httpx.RequestError as e:
                if isinstance(e, httpx.TimeoutException):
                    raise HATimeoutError(f"Timeout getting state for {validated.entity_id}", original_exception=e)
                elif isinstance(e, (httpx.ConnectError, httpx.NetworkError)):
                    raise HAConnectionError(f"Connection error getting state for {validated.entity_id}", original_exception=e)
                else:
                    raise HAClientError(f"Request error getting state for {validated.entity_id}: {str(e)}", original_exception=e)
        
        return await self.retry_manager.execute_with_retry(_get_state)
    
    async def get_all_states(self) -> List[HAEntityState]:
        """
        Get all entity states
        
        Returns:
            List of HAEntityState objects
        """
        response = await self.client.get("/api/states")
        response.raise_for_status()
        data = response.json()
        return [HAEntityState(**item) for item in data]

    async def get_exposed_entities(self, assistant_id: str = "conversation") -> List[HAEntityState]:
        """
        Get entities that are exposed to Home Assistant voice assistants
        
        Args:
            assistant_id: The assistant ID to check exposure for (default: "conversation")
            
        Returns:
            List of HAEntityState objects that are exposed to the specified assistant
            
        Raises:
            HAConnectionError: If there's a connection issue
            HAEntityNotFoundError: If the API endpoint is not available
        """
        try:
            # Try to get exposed entities from the conversation agent info
            response = await self.client.get("/api/conversation/agent/info")
            response.raise_for_status()
            agent_info = response.json()
            
            # Extract exposed entity IDs from the conversation agent info
            exposed_entity_ids = set()
            
            # The conversation agent info contains exposed entities in different formats
            if isinstance(agent_info, dict):
                # Look for entities in various possible locations in the response
                if "entities" in agent_info:
                    for entity_data in agent_info["entities"]:
                        if isinstance(entity_data, str):
                            exposed_entity_ids.add(entity_data)
                        elif isinstance(entity_data, dict) and "entity_id" in entity_data:
                            exposed_entity_ids.add(entity_data["entity_id"])
                
                # Also check in other possible locations
                for key in ["exposed_entities", "supported_entities", "entity_list"]:
                    if key in agent_info:
                        entities = agent_info[key]
                        if isinstance(entities, list):
                            for entity in entities:
                                if isinstance(entity, str):
                                    exposed_entity_ids.add(entity)
                                elif isinstance(entity, dict) and "entity_id" in entity:
                                    exposed_entity_ids.add(entity["entity_id"])
            
            # If we found exposed entities, get their full states
            if exposed_entity_ids:
                all_states = await self.get_all_states()
                exposed_states = [
                    state for state in all_states 
                    if state.entity_id in exposed_entity_ids
                ]
                return exposed_states
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # Conversation agent API not available, try fallback
                pass
            else:
                raise create_ha_error_from_response(e.response, e)
        except Exception:
            # Any other error, try fallback
            pass
        
        # Fallback: Use entity registry to find exposed entities
        return await self._get_exposed_entities_fallback(assistant_id)

    async def _get_exposed_entities_fallback(self, assistant_id: str = "conversation") -> List[HAEntityState]:
        """
        Fallback method to get exposed entities using the registry API
        """
        try:
            # Try entity registry API
            response = await self.client.get("/api/config/entity_registry/list")
            response.raise_for_status()
            registry_data = response.json()
            
            # Filter entities that are exposed to the conversation assistant
            exposed_entity_ids = set()
            for entity in registry_data:
                if isinstance(entity, dict):
                    # Check if entity is exposed to conversation
                    entity_options = entity.get("options", {})
                    conversation_options = entity_options.get("conversation", {})
                    
                    # Entity is exposed if it's not explicitly excluded
                    should_expose = conversation_options.get("should_expose", True)
                    if should_expose:
                        exposed_entity_ids.add(entity["entity_id"])
            
            # Get states for exposed entities
            if exposed_entity_ids:
                all_states = await self.get_all_states()
                exposed_states = [
                    state for state in all_states 
                    if state.entity_id in exposed_entity_ids
                ]
                return exposed_states
                
        except Exception:
            # Registry API also failed, return all entities
            pass
        
        # Ultimate fallback: return all entities (user can configure exposure in HA)
        logger.warning("Could not determine exposed entities, returning all entities. "
                      "Configure entity exposure in Home Assistant at: "
                      "/config/voice-assistants/expose?assistants=conversation")
        return await self.get_all_states()
    
    async def call_service(self, domain: str, service: str, service_data: Optional[Dict[str, Any]] = None, target: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Call a Home Assistant service
        
        Args:
            domain: Service domain (e.g., "light", "switch", "climate")
            service: Service name (e.g., "turn_on", "turn_off")
            service_data: Optional service data dictionary
            target: Optional target dictionary for entity selection
            
        Returns:
            Service call response data
            
        Raises:
            HAClientError: If the service call fails after retries
        """
        async def _call_service():
            try:
                logger.debug(f"Calling service: {domain}.{service}")
                payload = {}
                if service_data:
                    payload.update(service_data)
                if target:
                    payload["target"] = target
                    
                response = await self.client.post(
                    f"/api/services/{domain}/{service}",
                    json=payload
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 400:
                    # Bad request - likely invalid service or parameters
                    error_msg = f"Invalid service call: {domain}.{service}"
                    try:
                        error_data = e.response.json()
                        if 'message' in error_data:
                            error_msg = error_data['message']
                    except:
                        pass
                    raise HAAPIError(error_msg, status_code=400, original_exception=e)
                raise create_ha_error_from_response(e.response, e)
            except httpx.RequestError as e:
                if isinstance(e, httpx.TimeoutException):
                    raise HATimeoutError(f"Timeout calling service {domain}.{service}", original_exception=e)
                elif isinstance(e, (httpx.ConnectError, httpx.NetworkError)):
                    raise HAConnectionError(f"Connection error calling service {domain}.{service}", original_exception=e)
                else:
                    raise HAClientError(f"Request error calling service {domain}.{service}: {str(e)}", original_exception=e)
        
        return await self.retry_manager.execute_with_retry(_call_service)

    # Light Control Methods
    async def control_light(
        self, 
        entity_id: str, 
        state: str, 
        brightness: Optional[int] = None, 
        rgb_color: Optional[List[int]] = None,
        color_temp: Optional[int] = None,
        hs_color: Optional[List[float]] = None,
        transition: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Control a light entity with comprehensive options
        
        Args:
            entity_id: Light entity ID
            state: "on" or "off"
            brightness: Brightness level (0-255)
            rgb_color: RGB color as [r, g, b] (0-255 each)
            color_temp: Color temperature in mireds
            hs_color: Hue-Saturation as [hue, saturation] (hue: 0-360, sat: 0-100)
            transition: Transition time in seconds
            
        Returns:
            Service call response
            
        Raises:
            HAValidationError: If input parameters are invalid
        """
        # Validate input parameters
        validated = _validate_input(
            LightControlModel,
            entity_id=entity_id,
            state=state,
            brightness=brightness,
            rgb_color=rgb_color,
            color_temp=color_temp,
            hs_color=hs_color,
            transition=transition
        )
        
        service_data = {"entity_id": validated.entity_id}
        
        if validated.state == "on":
            if validated.brightness is not None:
                service_data["brightness"] = validated.brightness
            if validated.rgb_color is not None:
                service_data["rgb_color"] = validated.rgb_color
            if validated.color_temp is not None:
                service_data["color_temp"] = validated.color_temp
            if validated.hs_color is not None:
                service_data["hs_color"] = validated.hs_color
            if validated.transition is not None:
                service_data["transition"] = validated.transition
                
        return await self.call_service("light", f"turn_{validated.state}", service_data)

    # Switch Control Methods
    async def control_switch(self, entity_id: str, state: str) -> Dict[str, Any]:
        """
        Control a switch entity
        
        Args:
            entity_id: Switch entity ID
            state: "on" or "off"
            
        Returns:
            Service call response
            
        Raises:
            HAValidationError: If input parameters are invalid
        """
        # Validate input parameters
        validated = _validate_input(
            SwitchControlModel,
            entity_id=entity_id,
            state=state
        )
        
        service_data = {"entity_id": validated.entity_id}
        return await self.call_service("switch", f"turn_{validated.state}", service_data)

    # Climate Control Methods
    async def control_climate(
        self, 
        entity_id: str,
        hvac_mode: Optional[str] = None,
        temperature: Optional[float] = None,
        target_temp_high: Optional[float] = None,
        target_temp_low: Optional[float] = None,
        fan_mode: Optional[str] = None,
        swing_mode: Optional[str] = None,
        humidity: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Control a climate entity (thermostat, AC, etc.)
        
        Args:
            entity_id: Climate entity ID
            hvac_mode: HVAC mode (heat, cool, auto, off, etc.)
            temperature: Target temperature
            target_temp_high: High target temperature for range
            target_temp_low: Low target temperature for range
            fan_mode: Fan mode
            swing_mode: Swing mode
            humidity: Target humidity percentage
            
        Returns:
            Service call response
        """
        service_data = {"entity_id": entity_id}
        
        if hvac_mode is not None:
            service_data["hvac_mode"] = hvac_mode
        if temperature is not None:
            service_data["temperature"] = temperature
        if target_temp_high is not None:
            service_data["target_temp_high"] = target_temp_high
        if target_temp_low is not None:
            service_data["target_temp_low"] = target_temp_low
        if fan_mode is not None:
            service_data["fan_mode"] = fan_mode
        if swing_mode is not None:
            service_data["swing_mode"] = swing_mode
        if humidity is not None:
            service_data["humidity"] = humidity
            
        return await self.call_service("climate", "set_temperature", service_data)

    # Media Player Control Methods
    async def control_media_player(
        self,
        entity_id: str,
        action: str,
        media_content_id: Optional[str] = None,
        media_content_type: Optional[str] = None,
        volume_level: Optional[float] = None,
        source: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Control a media player entity
        
        Args:
            entity_id: Media player entity ID
            action: Action to perform (play, pause, stop, next, previous, etc.)
            media_content_id: Media content ID to play
            media_content_type: Type of media content
            volume_level: Volume level (0.0-1.0)
            source: Input source
            
        Returns:
            Service call response
        """
        service_data = {"entity_id": entity_id}
        
        if action == "play_media" and media_content_id and media_content_type:
            service_data["media_content_id"] = media_content_id
            service_data["media_content_type"] = media_content_type
        elif action == "volume_set" and volume_level is not None:
            service_data["volume_level"] = max(0.0, min(1.0, volume_level))
        elif action == "select_source" and source is not None:
            service_data["source"] = source
            
        return await self.call_service("media_player", action, service_data)

    # Cover Control Methods
    async def control_cover(
        self,
        entity_id: str,
        action: str,
        position: Optional[int] = None,
        tilt_position: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Control a cover entity (blinds, garage door, etc.)
        
        Args:
            entity_id: Cover entity ID
            action: Action (open_cover, close_cover, stop_cover, set_cover_position, etc.)
            position: Position percentage (0-100)
            tilt_position: Tilt position percentage (0-100)
            
        Returns:
            Service call response
        """
        service_data = {"entity_id": entity_id}
        
        if action == "set_cover_position" and position is not None:
            service_data["position"] = max(0, min(100, position))
        elif action == "set_cover_tilt_position" and tilt_position is not None:
            service_data["tilt_position"] = max(0, min(100, tilt_position))
            
        return await self.call_service("cover", action, service_data)

    # Fan Control Methods
    async def control_fan(
        self,
        entity_id: str,
        state: str,
        percentage: Optional[int] = None,
        preset_mode: Optional[str] = None,
        direction: Optional[str] = None,
        oscillating: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Control a fan entity
        
        Args:
            entity_id: Fan entity ID
            state: "on" or "off"
            percentage: Speed percentage (0-100)
            preset_mode: Preset mode
            direction: Direction (forward/reverse)
            oscillating: Oscillation state
            
        Returns:
            Service call response
        """
        service_data = {"entity_id": entity_id}
        
        if state == "on":
            if percentage is not None:
                service_data["percentage"] = max(0, min(100, percentage))
            if preset_mode is not None:
                service_data["preset_mode"] = preset_mode
            if direction is not None:
                service_data["direction"] = direction
            if oscillating is not None:
                service_data["oscillating"] = oscillating
                
        return await self.call_service("fan", f"turn_{state}", service_data)

    # Scene Control Methods
    async def activate_scene(self, entity_id: str, transition: Optional[int] = None) -> Dict[str, Any]:
        """
        Activate a scene
        
        Args:
            entity_id: Scene entity ID
            transition: Transition time in seconds
            
        Returns:
            Service call response
        """
        service_data = {"entity_id": entity_id}
        if transition is not None:
            service_data["transition"] = transition
            
        return await self.call_service("scene", "turn_on", service_data)

    # Script Control Methods
    async def run_script(self, entity_id: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Run a script
        
        Args:
            entity_id: Script entity ID
            variables: Variables to pass to the script
            
        Returns:
            Service call response
        """
        service_data = {"entity_id": entity_id}
        if variables:
            service_data.update(variables)
            
        return await self.call_service("script", "turn_on", service_data)

    # Automation Control Methods
    async def control_automation(self, entity_id: str, action: str) -> Dict[str, Any]:
        """
        Control an automation
        
        Args:
            entity_id: Automation entity ID
            action: Action (turn_on, turn_off, trigger, reload)
            
        Returns:
            Service call response
        """
        service_data = {"entity_id": entity_id}
        return await self.call_service("automation", action, service_data)

    # Input Control Methods
    async def set_input_boolean(self, entity_id: str, state: str) -> Dict[str, Any]:
        """Set input boolean state"""
        service_data = {"entity_id": entity_id}
        return await self.call_service("input_boolean", f"turn_{state}", service_data)

    async def set_input_number(self, entity_id: str, value: float) -> Dict[str, Any]:
        """Set input number value"""
        service_data = {"entity_id": entity_id, "value": value}
        return await self.call_service("input_number", "set_value", service_data)

    async def set_input_select(self, entity_id: str, option: str) -> Dict[str, Any]:
        """Set input select option"""
        service_data = {"entity_id": entity_id, "option": option}
        return await self.call_service("input_select", "select_option", service_data)

    async def set_input_text(self, entity_id: str, value: str) -> Dict[str, Any]:
        """Set input text value"""
        service_data = {"entity_id": entity_id, "value": value}
        return await self.call_service("input_text", "set_value", service_data)

    async def set_input_datetime(self, entity_id: str, datetime: Optional[str] = None, date: Optional[str] = None, time: Optional[str] = None) -> Dict[str, Any]:
        """Set input datetime value"""
        service_data = {"entity_id": entity_id}
        if datetime:
            service_data["datetime"] = datetime
        if date:
            service_data["date"] = date
        if time:
            service_data["time"] = time
        return await self.call_service("input_datetime", "set_datetime", service_data)

    # Utility Methods
    async def check_api_status(self) -> Dict[str, Any]:
        """
        Check Home Assistant API status
        
        Returns:
            API status information
            
        Raises:
            HAClientError: If the API check fails after retries
        """
        async def _check_status():
            try:
                logger.debug("Checking API status")
                response = await self.client.get("/api/")
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                raise create_ha_error_from_response(e.response, e)
            except httpx.RequestError as e:
                if isinstance(e, httpx.TimeoutException):
                    raise HATimeoutError("Timeout checking API status", original_exception=e)
                elif isinstance(e, (httpx.ConnectError, httpx.NetworkError)):
                    raise HAConnectionError("Connection error checking API status", original_exception=e)
                else:
                    raise HAClientError(f"Request error checking API status: {str(e)}", original_exception=e)
        
        return await self.retry_manager.execute_with_retry(_check_status)

    async def get_ha_config(self) -> Dict[str, Any]:
        """
        Get Home Assistant configuration from the API
        
        Returns:
            Configuration information from Home Assistant
            
        Raises:
            HAClientError: If getting configuration fails after retries
        """
        async def _get_config():
            try:
                logger.debug("Getting HA configuration")
                response = await self.client.get("/api/config")
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                raise create_ha_error_from_response(e.response, e)
            except httpx.RequestError as e:
                if isinstance(e, httpx.TimeoutException):
                    raise HATimeoutError("Timeout getting configuration", original_exception=e)
                elif isinstance(e, (httpx.ConnectError, httpx.NetworkError)):
                    raise HAConnectionError("Connection error getting configuration", original_exception=e)
                else:
                    raise HAClientError(f"Request error getting configuration: {str(e)}", original_exception=e)
        
        return await self.retry_manager.execute_with_retry(_get_config)

    async def get_services(self) -> Dict[str, Any]:
        """
        Get available services organized by domain
        
        Returns:
            Dictionary with domain names as keys and their services as values
            
        Raises:
            HAClientError: If getting services fails after retries
        """
        async def _get_services():
            try:
                logger.debug("Getting available services")
                response = await self.client.get("/api/services")
                response.raise_for_status()
                services_list = response.json()
                
                # Convert list of service domains to dict format
                services_dict = {}
                if isinstance(services_list, list):
                    for domain_info in services_list:
                        if isinstance(domain_info, dict) and 'domain' in domain_info:
                            domain = domain_info['domain']
                            services_dict[domain] = domain_info.get('services', {})
                else:
                    # If it's already a dict, return as-is (backward compatibility)
                    services_dict = services_list
                
                return services_dict
            except httpx.HTTPStatusError as e:
                raise create_ha_error_from_response(e.response, e)
            except httpx.RequestError as e:
                if isinstance(e, httpx.TimeoutException):
                    raise HATimeoutError("Timeout getting services", original_exception=e)
                elif isinstance(e, (httpx.ConnectError, httpx.NetworkError)):
                    raise HAConnectionError("Connection error getting services", original_exception=e)
                else:
                    raise HAClientError(f"Request error getting services: {str(e)}", original_exception=e)
        
        return await self.retry_manager.execute_with_retry(_get_services)
    
    # Batch Operations
    async def batch_get_states(self, entity_ids: List[str]) -> Dict[str, HAEntityState]:
        """
        Get states for multiple entities concurrently
        
        Args:
            entity_ids: List of entity IDs to retrieve states for
            
        Returns:
            Dictionary mapping entity_id to HAEntityState (successful only)
            
        Raises:
            HAValidationError: If entity_ids format is invalid
        """
        # Validate input
        validated = _validate_input(BatchEntityOperation, entity_ids=entity_ids)
        
        async def get_single_state(entity_id: str) -> tuple[str, Optional[HAEntityState]]:
            """Get state for a single entity, returning None on error"""
            try:
                state = await self.get_entity_state(entity_id)
                return entity_id, state
            except Exception as e:
                logger.warning(f"Failed to get state for {entity_id}: {e}")
                return entity_id, None
        
        # Execute all requests concurrently
        results = await asyncio.gather(
            *[get_single_state(entity_id) for entity_id in validated.entity_ids],
            return_exceptions=True
        )
        
        # Filter successful results
        successful_states = {}
        for result in results:
            if isinstance(result, tuple) and result[1] is not None:
                entity_id, state = result
                successful_states[entity_id] = state
        
        logger.info(f"Retrieved states for {len(successful_states)}/{len(validated.entity_ids)} entities")
        return successful_states
    
    async def batch_call_services(self, service_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Execute multiple service calls concurrently
        
        Args:
            service_calls: List of service call dictionaries with keys:
                - domain: Service domain
                - service: Service name  
                - service_data: Optional service data
                - target: Optional target
                
        Returns:
            List of results (successful calls only)
            
        Raises:
            HAValidationError: If service call format is invalid
        """
        # Validate each service call
        validated_calls = []
        for call in service_calls:
            validated = _validate_input(ServiceCallModel, **call)
            validated_calls.append(validated)
        
        async def execute_single_call(call: ServiceCallModel) -> Optional[Dict[str, Any]]:
            """Execute a single service call, returning None on error"""
            try:
                result = await self.call_service(
                    call.domain, 
                    call.service, 
                    call.service_data, 
                    call.target
                )
                return result
            except Exception as e:
                logger.warning(f"Failed service call {call.domain}.{call.service}: {e}")
                return None
        
        # Execute all service calls concurrently
        results = await asyncio.gather(
            *[execute_single_call(call) for call in validated_calls],
            return_exceptions=True
        )
        
        # Filter successful results
        successful_results = [
            result for result in results 
            if result is not None and not isinstance(result, Exception)
        ]
        
        logger.info(f"Executed {len(successful_results)}/{len(validated_calls)} service calls successfully")
        return successful_results
    
    async def batch_control_lights(
        self, 
        light_controls: List[Dict[str, Any]]
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Control multiple lights concurrently
        
        Args:
            light_controls: List of light control dictionaries with keys:
                - entity_id: Light entity ID
                - state: "on" or "off"
                - brightness: Optional brightness (0-255)
                - rgb_color: Optional RGB color [r, g, b]
                - color_temp: Optional color temperature
                - hs_color: Optional HS color [hue, saturation]
                - transition: Optional transition time
                
        Returns:
            Dictionary mapping entity_id to result (None if failed)
        """
        # Validate each light control
        validated_controls = []
        for control in light_controls:
            validated = _validate_input(LightControlModel, **control)
            validated_controls.append(validated)
        
        async def control_single_light(control: LightControlModel) -> tuple[str, Optional[Dict[str, Any]]]:
            """Control a single light, returning None on error"""
            try:
                result = await self.control_light(
                    control.entity_id,
                    control.state,
                    control.brightness,
                    control.rgb_color,
                    control.color_temp,
                    control.hs_color,
                    control.transition
                )
                return control.entity_id, result
            except Exception as e:
                logger.warning(f"Failed to control light {control.entity_id}: {e}")
                return control.entity_id, None
        
        # Execute all light controls concurrently
        results = await asyncio.gather(
            *[control_single_light(control) for control in validated_controls],
            return_exceptions=True
        )
        
        # Build results dictionary
        light_results = {}
        for result in results:
            if isinstance(result, tuple):
                entity_id, control_result = result
                light_results[entity_id] = control_result
        
        successful_count = sum(1 for result in light_results.values() if result is not None)
        logger.info(f"Controlled {successful_count}/{len(validated_controls)} lights successfully")
        return light_results
    
    async def batch_control_switches(
        self, 
        switch_controls: List[Dict[str, Any]]
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Control multiple switches concurrently
        
        Args:
            switch_controls: List of switch control dictionaries with keys:
                - entity_id: Switch entity ID
                - state: "on" or "off"
                
        Returns:
            Dictionary mapping entity_id to result (None if failed)
        """
        # Validate each switch control
        validated_controls = []
        for control in switch_controls:
            validated = _validate_input(SwitchControlModel, **control)
            validated_controls.append(validated)
        
        async def control_single_switch(control: SwitchControlModel) -> tuple[str, Optional[Dict[str, Any]]]:
            """Control a single switch, returning None on error"""
            try:
                result = await self.control_switch(control.entity_id, control.state)
                return control.entity_id, result
            except Exception as e:
                logger.warning(f"Failed to control switch {control.entity_id}: {e}")
                return control.entity_id, None
        
        # Execute all switch controls concurrently
        results = await asyncio.gather(
            *[control_single_switch(control) for control in validated_controls],
            return_exceptions=True
        )
        
        # Build results dictionary
        switch_results = {}
        for result in results:
            if isinstance(result, tuple):
                entity_id, control_result = result
                switch_results[entity_id] = control_result
        
        successful_count = sum(1 for result in switch_results.values() if result is not None)
        logger.info(f"Controlled {successful_count}/{len(validated_controls)} switches successfully")
        return switch_results
    
    async def batch_activate_scenes(self, scene_ids: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Activate multiple scenes concurrently
        
        Args:
            scene_ids: List of scene entity IDs
            
        Returns:
            Dictionary mapping scene_id to result (None if failed)
        """
        # Validate entity IDs
        validated = _validate_input(BatchEntityOperation, entity_ids=scene_ids)
        
        async def activate_single_scene(scene_id: str) -> tuple[str, Optional[Dict[str, Any]]]:
            """Activate a single scene, returning None on error"""
            try:
                result = await self.activate_scene(scene_id)
                return scene_id, result
            except Exception as e:
                logger.warning(f"Failed to activate scene {scene_id}: {e}")
                return scene_id, None
        
        # Execute all scene activations concurrently
        results = await asyncio.gather(
            *[activate_single_scene(scene_id) for scene_id in validated.entity_ids],
            return_exceptions=True
        )
        
        # Build results dictionary
        scene_results = {}
        for result in results:
            if isinstance(result, tuple):
                scene_id, activation_result = result
                scene_results[scene_id] = activation_result
        
        successful_count = sum(1 for result in scene_results.values() if result is not None)
        logger.info(f"Activated {successful_count}/{len(validated.entity_ids)} scenes successfully")
        return scene_results 