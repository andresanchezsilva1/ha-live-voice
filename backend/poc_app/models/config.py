"""
Modelos de configuração com validação usando Pydantic
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator, ConfigDict
from enum import Enum
import os
import re


class LogLevel(str, Enum):
    """Níveis de log disponíveis"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class GeminiModelConfig(BaseModel):
    """Configuração do modelo Gemini"""
    model_config = ConfigDict(frozen=True)
    
    model_name: str = Field(
        default="gemini-2.0-flash-exp",
        description="Nome do modelo Gemini Live API"
    )
    api_key: str = Field(
        ...,
        description="Chave da API do Google Gemini",
        min_length=1
    )
    max_tokens: int = Field(
        default=8192,
        ge=1,
        le=32768,
        description="Número máximo de tokens por resposta"
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Temperatura para controle de criatividade"
    )
    
    @field_validator('api_key')
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """Valida formato da chave API do Gemini"""
        if not v or v.strip() == "":
            raise ValueError("API key do Gemini não pode estar vazia")
        
        # Formato típico das chaves Google: AIza...
        if not v.startswith("AIza"):
            raise ValueError("Formato de API key do Gemini inválido (deve começar com 'AIza')")
        
        if len(v) < 30:
            raise ValueError("API key do Gemini muito curta")
            
        return v.strip()


class HomeAssistantConfig(BaseModel):
    """Configuração do Home Assistant"""
    model_config = ConfigDict(frozen=True)
    
    url: str = Field(
        ...,
        description="URL do Home Assistant",
        min_length=1
    )
    access_token: str = Field(
        ...,
        description="Token de acesso do Home Assistant",
        min_length=1
    )
    timeout: int = Field(
        default=30,
        ge=5,
        le=300,
        description="Timeout para requisições HTTP (segundos)"
    )
    verify_ssl: bool = Field(
        default=True,
        description="Verificar certificados SSL"
    )
    
    @field_validator('url')
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Valida URL do Home Assistant"""
        if not v or v.strip() == "":
            raise ValueError("URL do Home Assistant não pode estar vazia")
        
        url = v.strip()
        
        # Deve começar com http:// ou https://
        if not re.match(r'^https?://', url):
            raise ValueError("URL deve começar com http:// ou https://")
        
        # Deve ter formato válido de URL
        url_pattern = r'^https?://[^\s/$.?#].[^\s]*$'
        if not re.match(url_pattern, url):
            raise ValueError("Formato de URL inválido")
            
        # Remove trailing slash
        return url.rstrip('/')
    
    @field_validator('access_token')
    @classmethod
    def validate_access_token(cls, v: str) -> str:
        """Valida token de acesso"""
        if not v or v.strip() == "":
            raise ValueError("Access token do Home Assistant não pode estar vazio")
        
        token = v.strip()
        
        # Tokens do HA geralmente são longos
        if len(token) < 50:
            raise ValueError("Access token muito curto (deve ter pelo menos 50 caracteres)")
        
        return token


class WebSocketConfig(BaseModel):
    """Configuração do WebSocket"""
    model_config = ConfigDict(frozen=True)
    
    host: str = Field(
        default="localhost",
        description="Host do servidor WebSocket"
    )
    port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="Porta do servidor WebSocket"
    )
    max_connections: int = Field(
        default=100,
        ge=1,
        le=10000,
        description="Número máximo de conexões simultâneas"
    )
    ping_interval: int = Field(
        default=20,
        ge=5,
        le=300,
        description="Intervalo de ping em segundos"
    )
    ping_timeout: int = Field(
        default=20,
        ge=5,
        le=300,
        description="Timeout de ping em segundos"
    )


class SessionConfig(BaseModel):
    """Configuração de sessões"""
    model_config = ConfigDict(frozen=True)
    
    max_session_age_minutes: int = Field(
        default=30,
        ge=1,
        le=1440,  # 24 horas
        description="Idade máxima da sessão em minutos"
    )
    cleanup_interval_seconds: int = Field(
        default=60,
        ge=10,
        le=3600,
        description="Intervalo de limpeza de sessões em segundos"
    )
    max_audio_buffer_size: int = Field(
        default=1024 * 1024,  # 1MB
        ge=1024,
        le=10 * 1024 * 1024,  # 10MB
        description="Tamanho máximo do buffer de áudio em bytes"
    )
    audio_chunk_timeout: int = Field(
        default=30,
        ge=5,
        le=300,
        description="Timeout para processamento de chunk de áudio em segundos"
    )


class LoggingConfig(BaseModel):
    """Configuração de logging"""
    model_config = ConfigDict(frozen=True)
    
    level: LogLevel = Field(
        default=LogLevel.INFO,
        description="Nível de log"
    )
    file_path: Optional[str] = Field(
        default=None,
        description="Caminho para arquivo de log (opcional)"
    )
    max_file_size: int = Field(
        default=10 * 1024 * 1024,  # 10MB
        ge=1024 * 1024,  # 1MB mínimo
        le=100 * 1024 * 1024,  # 100MB máximo
        description="Tamanho máximo do arquivo de log em bytes"
    )
    backup_count: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Número de arquivos de backup"
    )
    format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        min_length=10,
        description="Formato das mensagens de log"
    )


class ApplicationConfig(BaseModel):
    """Configuração principal da aplicação"""
    model_config = ConfigDict(frozen=True)
    
    # Configurações dos componentes
    gemini: GeminiModelConfig
    home_assistant: HomeAssistantConfig
    websocket: WebSocketConfig = Field(default_factory=WebSocketConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    
    # Configurações gerais
    app_name: str = Field(
        default="Home Assistant Voice Control",
        min_length=1,
        description="Nome da aplicação"
    )
    version: str = Field(
        default="1.0.0",
        pattern=r'^\d+\.\d+\.\d+$',
        description="Versão da aplicação (formato semver)"
    )
    debug: bool = Field(
        default=False,
        description="Modo debug ativado"
    )
    
    @classmethod
    def from_env(cls) -> 'ApplicationConfig':
        """
        Cria configuração a partir de variáveis de ambiente
        
        Returns:
            ApplicationConfig: Configuração validada
            
        Raises:
            ValueError: Se configurações obrigatórias estão ausentes
        """
        # Carregar variáveis obrigatórias
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key:
            raise ValueError("Variável de ambiente GEMINI_API_KEY é obrigatória")
        
        ha_url = os.getenv("HA_URL")
        if not ha_url:
            raise ValueError("Variável de ambiente HA_URL é obrigatória")
        
        ha_token = os.getenv("HA_LLAT")
        if not ha_token:
            raise ValueError("Variável de ambiente HA_LLAT é obrigatória")
        
        # Configurações opcionais
        gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")
        gemini_max_tokens = int(os.getenv("GEMINI_MAX_TOKENS", "8192"))
        gemini_temperature = float(os.getenv("GEMINI_TEMPERATURE", "0.7"))
        
        ws_host = os.getenv("WS_HOST", "localhost")
        ws_port = int(os.getenv("WS_PORT", "8000"))
        
        log_level = os.getenv("LOG_LEVEL", "INFO")
        log_file = os.getenv("LOG_FILE")
        
        debug_mode = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")
        
        return cls(
            gemini=GeminiModelConfig(
                model_name=gemini_model,
                api_key=gemini_api_key,
                max_tokens=gemini_max_tokens,
                temperature=gemini_temperature
            ),
            home_assistant=HomeAssistantConfig(
                url=ha_url,
                access_token=ha_token,
                timeout=int(os.getenv("HA_TIMEOUT", "30")),
                verify_ssl=os.getenv("HA_VERIFY_SSL", "true").lower() in ("true", "1", "yes")
            ),
            websocket=WebSocketConfig(
                host=ws_host,
                port=ws_port,
                max_connections=int(os.getenv("WS_MAX_CONNECTIONS", "100")),
                ping_interval=int(os.getenv("WS_PING_INTERVAL", "20")),
                ping_timeout=int(os.getenv("WS_PING_TIMEOUT", "20"))
            ),
            session=SessionConfig(
                max_session_age_minutes=int(os.getenv("SESSION_MAX_AGE_MINUTES", "30")),
                cleanup_interval_seconds=int(os.getenv("SESSION_CLEANUP_INTERVAL", "60")),
                max_audio_buffer_size=int(os.getenv("MAX_AUDIO_BUFFER_SIZE", str(1024 * 1024))),
                audio_chunk_timeout=int(os.getenv("AUDIO_CHUNK_TIMEOUT", "30"))
            ),
            logging=LoggingConfig(
                level=LogLevel(log_level),
                file_path=log_file,
                max_file_size=int(os.getenv("LOG_MAX_FILE_SIZE", str(10 * 1024 * 1024))),
                backup_count=int(os.getenv("LOG_BACKUP_COUNT", "5")),
                format=os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            ),
            app_name=os.getenv("APP_NAME", "Home Assistant Voice Control"),
            version=os.getenv("APP_VERSION", "1.0.0"),
            debug=debug_mode
        )
    
    def validate_connectivity(self) -> Dict[str, Any]:
        """
        Valida conectividade com serviços externos
        
        Returns:
            Dict com status de validação
        """
        results = {
            "gemini_api": {"status": "unknown", "message": ""},
            "home_assistant": {"status": "unknown", "message": ""},
            "overall": {"status": "unknown", "valid": False}
        }
        
        # Validar formato das configurações (já feito pelo Pydantic)
        try:
            # Para Gemini, só podemos validar formato da API key
            if self.gemini.api_key.startswith("AIza"):
                results["gemini_api"]["status"] = "valid_format"
                results["gemini_api"]["message"] = "Formato da API key válido"
            else:
                results["gemini_api"]["status"] = "invalid_format"
                results["gemini_api"]["message"] = "Formato da API key inválido"
            
            # Para HA, validar URL
            if self.home_assistant.url.startswith(("http://", "https://")):
                results["home_assistant"]["status"] = "valid_format"
                results["home_assistant"]["message"] = "Formato da URL válido"
            else:
                results["home_assistant"]["status"] = "invalid_format"
                results["home_assistant"]["message"] = "Formato da URL inválido"
            
            # Status geral
            all_valid = (
                results["gemini_api"]["status"] == "valid_format" and
                results["home_assistant"]["status"] == "valid_format"
            )
            
            results["overall"]["status"] = "valid" if all_valid else "invalid"
            results["overall"]["valid"] = all_valid
            
        except Exception as e:
            results["overall"]["status"] = "error"
            results["overall"]["message"] = str(e)
            results["overall"]["valid"] = False
        
        return results
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte configuração para dicionário (sem dados sensíveis)"""
        config_dict = self.model_dump()
        
        # Mascarar dados sensíveis
        if "gemini" in config_dict and "api_key" in config_dict["gemini"]:
            config_dict["gemini"]["api_key"] = self._mask_sensitive_data(config_dict["gemini"]["api_key"])
        
        if "home_assistant" in config_dict and "access_token" in config_dict["home_assistant"]:
            config_dict["home_assistant"]["access_token"] = self._mask_sensitive_data(config_dict["home_assistant"]["access_token"])
        
        return config_dict
    
    @staticmethod
    def _mask_sensitive_data(data: str, visible_chars: int = 8) -> str:
        """Mascara dados sensíveis mostrando apenas os primeiros caracteres"""
        if len(data) <= visible_chars:
            return "*" * len(data)
        return data[:visible_chars] + "*" * (len(data) - visible_chars) 