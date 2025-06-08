"""
Pydantic models for Home Assistant client input validation

This module defines comprehensive validation models for all device types
and service calls supported by the HomeAssistantClient.
"""

from typing import Any, Dict, List, Optional, Union, Literal
from pydantic import BaseModel, Field, field_validator, model_validator
import re
from enum import Enum


class EntityIdModel(BaseModel):
    """Base model for entity ID validation"""
    entity_id: str = Field(..., description="Home Assistant entity ID")
    
    @field_validator('entity_id')
    @classmethod
    def validate_entity_id(cls, v):
        """Validate entity ID format (domain.entity_name)"""
        if not isinstance(v, str):
            raise ValueError("Entity ID must be a string")
        
        # HA entity ID pattern: domain.entity_name
        pattern = r'^[a-z_]+\.[a-z0-9_]+$'
        if not re.match(pattern, v):
            raise ValueError(
                f"Invalid entity ID format: '{v}'. "
                "Must be in format 'domain.entity_name' (lowercase, underscores allowed)"
            )
        return v


class StateModel(BaseModel):
    """Model for basic state operations"""
    state: Literal["on", "off"] = Field(..., description="Device state")


class ColorModel(BaseModel):
    """Model for color validation"""
    rgb_color: Optional[List[int]] = Field(None, description="RGB color values [r, g, b]")
    hs_color: Optional[List[float]] = Field(None, description="Hue-Saturation color [hue, saturation]")
    color_temp: Optional[int] = Field(None, description="Color temperature in mireds")
    
    @field_validator('rgb_color')
    @classmethod
    def validate_rgb(cls, v):
        """Validate RGB color values"""
        if v is not None:
            if not isinstance(v, list) or len(v) != 3:
                raise ValueError("RGB color must be a list of 3 values")
            for i, color in enumerate(v):
                if not isinstance(color, int) or not 0 <= color <= 255:
                    raise ValueError(f"RGB value {i} must be integer between 0-255")
        return v
    
    @field_validator('hs_color')
    @classmethod
    def validate_hs(cls, v):
        """Validate Hue-Saturation color values"""
        if v is not None:
            if not isinstance(v, list) or len(v) != 2:
                raise ValueError("HS color must be a list of 2 values [hue, saturation]")
            hue, sat = v
            if not 0 <= hue <= 360:
                raise ValueError("Hue must be between 0-360")
            if not 0 <= sat <= 100:
                raise ValueError("Saturation must be between 0-100")
        return v
    
    @field_validator('color_temp')
    @classmethod
    def validate_color_temp(cls, v):
        """Validate color temperature"""
        if v is not None and (not isinstance(v, int) or not 153 <= v <= 500):
            raise ValueError("Color temperature must be between 153-500 mireds")
        return v


class LightControlModel(EntityIdModel, StateModel, ColorModel):
    """Model for light control parameters"""
    brightness: Optional[int] = Field(None, ge=0, le=255, description="Brightness level (0-255)")
    transition: Optional[int] = Field(None, ge=0, description="Transition time in seconds")
    
    @field_validator('brightness')
    @classmethod
    def validate_brightness(cls, v):
        """Validate brightness value"""
        if v is not None and (not isinstance(v, int) or not 0 <= v <= 255):
            raise ValueError("Brightness must be integer between 0-255")
        return v


class SwitchControlModel(EntityIdModel, StateModel):
    """Model for switch control parameters"""
    pass


class HVACMode(str, Enum):
    """HVAC operating modes"""
    OFF = "off"
    HEAT = "heat"
    COOL = "cool"
    AUTO = "auto"
    DRY = "dry"
    FAN_ONLY = "fan_only"
    HEAT_COOL = "heat_cool"


class ClimateControlModel(EntityIdModel):
    """Model for climate control parameters"""
    hvac_mode: Optional[HVACMode] = Field(None, description="HVAC mode")
    temperature: Optional[float] = Field(None, ge=-50, le=100, description="Target temperature")
    target_temp_high: Optional[float] = Field(None, ge=-50, le=100, description="High target temperature")
    target_temp_low: Optional[float] = Field(None, ge=-50, le=100, description="Low target temperature")
    fan_mode: Optional[str] = Field(None, description="Fan mode")
    swing_mode: Optional[str] = Field(None, description="Swing mode")
    humidity: Optional[int] = Field(None, ge=0, le=100, description="Target humidity percentage")
    
    @model_validator(mode="before")
    def validate_temperature_range(cls, values):
        """Validate temperature range consistency"""
        temp_high = values.get('target_temp_high')
        temp_low = values.get('target_temp_low')
        
        if temp_high is not None and temp_low is not None:
            if temp_high <= temp_low:
                raise ValueError("High temperature must be greater than low temperature")
        
        return values


class MediaPlayerAction(str, Enum):
    """Media player actions"""
    PLAY = "media_play"
    PAUSE = "media_pause"
    STOP = "media_stop"
    NEXT = "media_next_track"
    PREVIOUS = "media_previous_track"
    PLAY_MEDIA = "play_media"
    VOLUME_SET = "volume_set"
    VOLUME_UP = "volume_up"
    VOLUME_DOWN = "volume_down"
    VOLUME_MUTE = "volume_mute"
    SELECT_SOURCE = "select_source"


class MediaPlayerControlModel(EntityIdModel):
    """Model for media player control parameters"""
    action: MediaPlayerAction = Field(..., description="Action to perform")
    media_content_id: Optional[str] = Field(None, description="Media content ID")
    media_content_type: Optional[str] = Field(None, description="Media content type")
    volume_level: Optional[float] = Field(None, ge=0.0, le=1.0, description="Volume level (0.0-1.0)")
    source: Optional[str] = Field(None, description="Input source")
    
    @model_validator(mode="before")
    def validate_action_requirements(cls, values):
        """Validate action-specific requirements"""
        action = values.get('action')
        
        if action == MediaPlayerAction.PLAY_MEDIA:
            if not values.get('media_content_id') or not values.get('media_content_type'):
                raise ValueError("play_media action requires media_content_id and media_content_type")
        
        if action == MediaPlayerAction.VOLUME_SET:
            if values.get('volume_level') is None:
                raise ValueError("volume_set action requires volume_level")
        
        if action == MediaPlayerAction.SELECT_SOURCE:
            if not values.get('source'):
                raise ValueError("select_source action requires source")
        
        return values


class CoverAction(str, Enum):
    """Cover actions"""
    OPEN = "open_cover"
    CLOSE = "close_cover"
    STOP = "stop_cover"
    SET_POSITION = "set_cover_position"
    SET_TILT_POSITION = "set_cover_tilt_position"


class CoverControlModel(EntityIdModel):
    """Model for cover control parameters"""
    action: CoverAction = Field(..., description="Action to perform")
    position: Optional[int] = Field(None, ge=0, le=100, description="Position percentage (0-100)")
    tilt_position: Optional[int] = Field(None, ge=0, le=100, description="Tilt position percentage (0-100)")
    
    @model_validator(mode="before")
    def validate_action_requirements(cls, values):
        """Validate action-specific requirements"""
        action = values.get('action')
        
        if action == CoverAction.SET_POSITION:
            if values.get('position') is None:
                raise ValueError("set_cover_position action requires position")
        
        if action == CoverAction.SET_TILT_POSITION:
            if values.get('tilt_position') is None:
                raise ValueError("set_cover_tilt_position action requires tilt_position")
        
        return values


class FanControlModel(EntityIdModel, StateModel):
    """Model for fan control parameters"""
    percentage: Optional[int] = Field(None, ge=0, le=100, description="Speed percentage (0-100)")
    preset_mode: Optional[str] = Field(None, description="Preset mode")
    direction: Optional[Literal["forward", "reverse"]] = Field(None, description="Fan direction")
    oscillating: Optional[bool] = Field(None, description="Oscillation state")


class SceneControlModel(EntityIdModel):
    """Model for scene control parameters"""
    transition: Optional[int] = Field(None, ge=0, description="Transition time in seconds")


class ScriptControlModel(EntityIdModel):
    """Model for script control parameters"""
    variables: Optional[Dict[str, Any]] = Field(None, description="Variables to pass to script")


class AutomationAction(str, Enum):
    """Automation actions"""
    TURN_ON = "turn_on"
    TURN_OFF = "turn_off"
    TRIGGER = "trigger"
    RELOAD = "reload"


class AutomationControlModel(EntityIdModel):
    """Model for automation control parameters"""
    action: AutomationAction = Field(..., description="Action to perform")


class InputBooleanModel(EntityIdModel, StateModel):
    """Model for input boolean control"""
    pass


class InputNumberModel(EntityIdModel):
    """Model for input number control"""
    value: float = Field(..., description="Number value to set")


class InputSelectModel(EntityIdModel):
    """Model for input select control"""
    option: str = Field(..., description="Option to select")


class InputTextModel(EntityIdModel):
    """Model for input text control"""
    value: str = Field(..., max_length=255, description="Text value to set")


class InputDateTimeModel(EntityIdModel):
    """Model for input datetime control"""
    datetime: Optional[str] = Field(None, description="Datetime string (ISO format)")
    date: Optional[str] = Field(None, description="Date string (YYYY-MM-DD)")
    time: Optional[str] = Field(None, description="Time string (HH:MM:SS)")
    
    @field_validator('datetime')
    @classmethod
    def validate_datetime(cls, v):
        """Validate datetime format"""
        if v is not None:
            import datetime
            try:
                datetime.datetime.fromisoformat(v.replace('Z', '+00:00'))
            except ValueError:
                raise ValueError("Invalid datetime format, use ISO format")
        return v
    
    @field_validator('date')
    @classmethod
    def validate_date(cls, v):
        """Validate date format"""
        if v is not None:
            import datetime
            try:
                datetime.datetime.strptime(v, '%Y-%m-%d')
            except ValueError:
                raise ValueError("Invalid date format, use YYYY-MM-DD")
        return v
    
    @field_validator('time')
    @classmethod
    def validate_time(cls, v):
        """Validate time format"""
        if v is not None:
            import datetime
            try:
                datetime.datetime.strptime(v, '%H:%M:%S')
            except ValueError:
                raise ValueError("Invalid time format, use HH:MM:SS")
        return v
    
    @model_validator(mode="before")
    def validate_at_least_one(cls, values):
        """Ensure at least one time field is provided"""
        if not any([values.get('datetime'), values.get('date'), values.get('time')]):
            raise ValueError("At least one of datetime, date, or time must be provided")
        return values


class ServiceCallModel(BaseModel):
    """Model for generic service calls"""
    domain: str = Field(..., description="Service domain")
    service: str = Field(..., description="Service name")
    service_data: Optional[Dict[str, Any]] = Field(None, description="Service data")
    target: Optional[Dict[str, Any]] = Field(None, description="Service target")
    
    @field_validator('domain')
    @classmethod
    def validate_domain(cls, v):
        """Validate domain format"""
        if not re.match(r'^[a-z_]+$', v):
            raise ValueError("Domain must contain only lowercase letters and underscores")
        return v
    
    @field_validator('service')
    @classmethod
    def validate_service(cls, v):
        """Validate service format"""
        if not re.match(r'^[a-z_]+$', v):
            raise ValueError("Service must contain only lowercase letters and underscores")
        return v


class BatchEntityOperation(BaseModel):
    """Model for batch entity operations"""
    entity_ids: List[str] = Field(..., min_items=1, description="List of entity IDs")
    
    @field_validator('entity_ids')
    @classmethod
    def validate_entity_ids(cls, v):
        """Validate all entity IDs in the list"""
        for entity_id in v:
            # Reuse EntityIdModel validation
            EntityIdModel(entity_id=entity_id)
        return v


class BatchServiceCall(ServiceCallModel):
    """Model for batch service calls"""
    operations: List[Dict[str, Any]] = Field(..., min_items=1, description="List of operations")


# Export all models for easy imports
__all__ = [
    'EntityIdModel',
    'StateModel', 
    'ColorModel',
    'LightControlModel',
    'SwitchControlModel',
    'HVACMode',
    'ClimateControlModel',
    'MediaPlayerAction',
    'MediaPlayerControlModel', 
    'CoverAction',
    'CoverControlModel',
    'FanControlModel',
    'SceneControlModel',
    'ScriptControlModel',
    'AutomationAction',
    'AutomationControlModel',
    'InputBooleanModel',
    'InputNumberModel',
    'InputSelectModel',
    'InputTextModel',
    'InputDateTimeModel',
    'ServiceCallModel',
    'BatchEntityOperation',
    'BatchServiceCall'
] 