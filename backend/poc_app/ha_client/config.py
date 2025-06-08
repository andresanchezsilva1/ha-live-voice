"""Configuration management for Home Assistant client."""

import os
import json
from pathlib import Path
from typing import Optional, Dict, Any, Union
from pydantic import BaseModel, Field, field_validator
from pydantic.config import ConfigDict


class HAClientConfig(BaseModel):
    """Configuration model for Home Assistant client."""
    
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )
    
    base_url: str = Field(..., description="Home Assistant base URL")
    access_token: str = Field(..., description="Home Assistant long-lived access token")
    timeout: float = Field(default=10.0, ge=1.0, le=300.0, description="Request timeout in seconds")
    verify_ssl: bool = Field(default=True, description="Verify SSL certificates")
    max_retries: int = Field(default=3, ge=0, le=10, description="Maximum retry attempts")
    retry_delay: float = Field(default=1.0, ge=0.1, le=60.0, description="Base retry delay in seconds")
    circuit_breaker_threshold: int = Field(default=5, ge=1, le=20, description="Circuit breaker failure threshold")
    circuit_breaker_timeout: float = Field(default=60.0, ge=10.0, le=600.0, description="Circuit breaker recovery timeout")
    
    @field_validator('base_url')
    @classmethod
    def validate_base_url(cls, v):
        """Validate and normalize base URL."""
        if not v:
            raise ValueError("base_url cannot be empty")
        
        # Remove trailing slash
        v = v.rstrip('/')
        
        # Add protocol if missing
        if not v.startswith(('http://', 'https://')):
            v = f'http://{v}'
        
        return v
    
    @field_validator('access_token')
    @classmethod
    def validate_access_token(cls, v):
        """Validate access token."""
        if not v or len(v.strip()) < 10:
            raise ValueError("access_token must be at least 10 characters long")
        return v.strip()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return self.model_dump()
    
    def to_json(self) -> str:
        """Convert configuration to JSON string."""
        return self.model_dump_json(indent=2)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HAClientConfig':
        """Create configuration from dictionary."""
        return cls(**data)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'HAClientConfig':
        """Create configuration from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)


class ConfigManager:
    """Manages Home Assistant client configuration."""
    
    DEFAULT_CONFIG_PATHS = [
        Path.home() / '.ha_client' / 'config.json',
        Path.cwd() / '.ha_client.json',
        Path.cwd() / 'ha_client_config.json'
    ]
    
    def __init__(self, config_path: Optional[Union[str, Path]] = None):
        """Initialize configuration manager.
        
        Args:
            config_path: Optional path to configuration file
        """
        self.config_path = Path(config_path) if config_path else None
        self._config: Optional[HAClientConfig] = None
    
    def load_from_env(self, prefix: str = 'HA_') -> HAClientConfig:
        """Load configuration from environment variables.
        
        Args:
            prefix: Environment variable prefix (default: 'HA_')
            
        Returns:
            HAClientConfig: Loaded configuration
            
        Raises:
            ValueError: If required environment variables are missing
        """
        env_mapping = {
            'base_url': f'{prefix}BASE_URL',
            'access_token': f'{prefix}ACCESS_TOKEN',
            'timeout': f'{prefix}TIMEOUT',
            'verify_ssl': f'{prefix}VERIFY_SSL',
            'max_retries': f'{prefix}MAX_RETRIES',
            'retry_delay': f'{prefix}RETRY_DELAY',
            'circuit_breaker_threshold': f'{prefix}CIRCUIT_BREAKER_THRESHOLD',
            'circuit_breaker_timeout': f'{prefix}CIRCUIT_BREAKER_TIMEOUT'
        }
        
        config_data = {}
        
        # Required fields
        required_fields = ['base_url', 'access_token']
        for field in required_fields:
            env_var = env_mapping[field]
            value = os.getenv(env_var)
            if not value:
                raise ValueError(f"Required environment variable {env_var} is not set")
            config_data[field] = value
        
        # Optional fields with type conversion
        optional_fields = {
            'timeout': float,
            'verify_ssl': lambda x: x.lower() in ('true', '1', 'yes', 'on'),
            'max_retries': int,
            'retry_delay': float,
            'circuit_breaker_threshold': int,
            'circuit_breaker_timeout': float
        }
        
        for field, converter in optional_fields.items():
            env_var = env_mapping[field]
            value = os.getenv(env_var)
            if value:
                try:
                    config_data[field] = converter(value)
                except (ValueError, TypeError) as e:
                    raise ValueError(f"Invalid value for {env_var}: {value}") from e
        
        self._config = HAClientConfig(**config_data)
        return self._config
    
    def load_from_file(self, config_path: Optional[Union[str, Path]] = None) -> HAClientConfig:
        """Load configuration from file.
        
        Args:
            config_path: Path to configuration file. If None, searches default paths.
            
        Returns:
            HAClientConfig: Loaded configuration
            
        Raises:
            FileNotFoundError: If configuration file is not found
            ValueError: If configuration file is invalid
        """
        if config_path:
            path = Path(config_path)
        elif self.config_path:
            path = self.config_path
        else:
            # Search default paths
            path = None
            for default_path in self.DEFAULT_CONFIG_PATHS:
                if default_path.exists():
                    path = default_path
                    break
            
            if not path:
                raise FileNotFoundError(
                    f"Configuration file not found in default locations: "
                    f"{[str(p) for p in self.DEFAULT_CONFIG_PATHS]}"
                )
        
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self._config = HAClientConfig.from_dict(data)
            self.config_path = path
            return self._config
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in configuration file {path}: {e}") from e
        except Exception as e:
            raise ValueError(f"Error loading configuration from {path}: {e}") from e
    
    def save_to_file(self, config: HAClientConfig, config_path: Optional[Union[str, Path]] = None) -> Path:
        """Save configuration to file.
        
        Args:
            config: Configuration to save
            config_path: Path to save configuration. If None, uses current config_path or default.
            
        Returns:
            Path: Path where configuration was saved
        """
        if config_path:
            path = Path(config_path)
        elif self.config_path:
            path = self.config_path
        else:
            path = self.DEFAULT_CONFIG_PATHS[0]
        
        # Create directory if it doesn't exist
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save configuration
        with open(path, 'w', encoding='utf-8') as f:
            f.write(config.to_json())
        
        self.config_path = path
        self._config = config
        return path
    
    def update_config(self, **kwargs) -> HAClientConfig:
        """Update current configuration with new values.
        
        Args:
            **kwargs: Configuration fields to update
            
        Returns:
            HAClientConfig: Updated configuration
            
        Raises:
            ValueError: If no configuration is loaded or invalid values provided
        """
        if not self._config:
            raise ValueError("No configuration loaded. Load configuration first.")
        
        # Create updated configuration
        current_data = self._config.to_dict()
        current_data.update(kwargs)
        
        self._config = HAClientConfig.from_dict(current_data)
        return self._config
    
    def get_config(self) -> Optional[HAClientConfig]:
        """Get current configuration.
        
        Returns:
            HAClientConfig or None: Current configuration if loaded
        """
        return self._config
    
    def create_sample_config(self, path: Optional[Union[str, Path]] = None) -> Path:
        """Create a sample configuration file.
        
        Args:
            path: Path to create sample configuration. If None, uses default.
            
        Returns:
            Path: Path where sample configuration was created
        """
        sample_config = HAClientConfig(
            base_url="http://homeassistant.local:8123",
            access_token="your_long_lived_access_token_here",
            timeout=10.0,
            verify_ssl=True,
            max_retries=3,
            retry_delay=1.0,
            circuit_breaker_threshold=5,
            circuit_breaker_timeout=60.0
        )
        
        if not path:
            path = Path.cwd() / 'ha_client_config.sample.json'
        else:
            path = Path(path)
        
        return self.save_to_file(sample_config, path) 