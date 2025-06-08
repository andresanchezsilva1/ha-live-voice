"""
Exceções customizadas para o sistema WebSocket.
Define tipos específicos de erro para melhor tratamento e logging.
"""

import logging
from typing import Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ErrorSeverity(str, Enum):
    """Níveis de severidade dos erros"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class WebSocketError(Exception):
    """Classe base para todas as exceções WebSocket"""
    
    def __init__(self, 
                 message: str, 
                 error_code: str = "WEBSOCKET_ERROR",
                 severity: ErrorSeverity = ErrorSeverity.MEDIUM,
                 connection_id: Optional[str] = None,
                 details: Optional[Dict[str, Any]] = None,
                 recoverable: bool = True):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.severity = severity
        self.connection_id = connection_id
        self.details = details or {}
        self.recoverable = recoverable
        
        # Log automático do erro
        self._log_error()
    
    def _log_error(self) -> None:
        """Log automático baseado na severidade"""
        log_msg = f"[{self.error_code}] {self.message}"
        if self.connection_id:
            log_msg += f" (Connection: {self.connection_id})"
        
        if self.severity == ErrorSeverity.CRITICAL:
            logger.critical(log_msg, extra=self.details)
        elif self.severity == ErrorSeverity.HIGH:
            logger.error(log_msg, extra=self.details)
        elif self.severity == ErrorSeverity.MEDIUM:
            logger.warning(log_msg, extra=self.details)
        else:
            logger.info(log_msg, extra=self.details)
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte a exceção para dicionário para serialização"""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "severity": self.severity.value,
            "connection_id": self.connection_id,
            "details": self.details,
            "recoverable": self.recoverable
        }


class ConnectionError(WebSocketError):
    """Erros relacionados à conexão WebSocket"""
    
    def __init__(self, message: str, connection_id: Optional[str] = None, **kwargs):
        super().__init__(
            message=message,
            error_code="CONNECTION_ERROR",
            severity=ErrorSeverity.HIGH,
            connection_id=connection_id,
            recoverable=True,
            **kwargs
        )


class MessageParsingError(WebSocketError):
    """Erros de parsing/validação de mensagens"""
    
    def __init__(self, message: str, raw_data: Any = None, connection_id: Optional[str] = None, **kwargs):
        details = {"raw_data_type": type(raw_data).__name__}
        if hasattr(raw_data, '__str__'):
            details["raw_data_preview"] = str(raw_data)[:100]
        
        super().__init__(
            message=message,
            error_code="MESSAGE_PARSING_ERROR",
            severity=ErrorSeverity.MEDIUM,
            connection_id=connection_id,
            details=details,
            recoverable=True,
            **kwargs
        )


class AudioProcessingError(WebSocketError):
    """Erros específicos de processamento de áudio"""
    
    def __init__(self, message: str, audio_format: Optional[str] = None, 
                 audio_size: Optional[int] = None, connection_id: Optional[str] = None, **kwargs):
        details = {}
        if audio_format:
            details["audio_format"] = audio_format
        if audio_size:
            details["audio_size"] = audio_size
            
        super().__init__(
            message=message,
            error_code="AUDIO_PROCESSING_ERROR",
            severity=ErrorSeverity.MEDIUM,
            connection_id=connection_id,
            details=details,
            recoverable=True,
            **kwargs
        )


class BroadcastError(WebSocketError):
    """Erros relacionados a operações de broadcast"""
    
    def __init__(self, message: str, failed_connections: Optional[int] = None, 
                 total_connections: Optional[int] = None, connection_id: Optional[str] = None, **kwargs):
        details = {}
        if failed_connections is not None:
            details["failed_connections"] = failed_connections
        if total_connections is not None:
            details["total_connections"] = total_connections
            
        super().__init__(
            message=message,
            error_code="BROADCAST_ERROR",
            severity=ErrorSeverity.MEDIUM,
            connection_id=connection_id,
            details=details,
            recoverable=True,
            **kwargs
        )


class ProtocolViolationError(WebSocketError):
    """Erros de violação do protocolo de mensagens"""
    
    def __init__(self, message: str, expected_type: Optional[str] = None, 
                 received_type: Optional[str] = None, connection_id: Optional[str] = None, **kwargs):
        details = {}
        if expected_type:
            details["expected_type"] = expected_type
        if received_type:
            details["received_type"] = received_type
            
        super().__init__(
            message=message,
            error_code="PROTOCOL_VIOLATION",
            severity=ErrorSeverity.HIGH,
            connection_id=connection_id,
            details=details,
            recoverable=True,
            **kwargs
        )


class RateLimitError(WebSocketError):
    """Erros de limite de taxa (rate limiting)"""
    
    def __init__(self, message: str, current_rate: Optional[float] = None, 
                 limit: Optional[float] = None, connection_id: Optional[str] = None, **kwargs):
        details = {}
        if current_rate is not None:
            details["current_rate"] = current_rate
        if limit is not None:
            details["rate_limit"] = limit
            
        super().__init__(
            message=message,
            error_code="RATE_LIMIT_EXCEEDED",
            severity=ErrorSeverity.MEDIUM,
            connection_id=connection_id,
            details=details,
            recoverable=True,
            **kwargs
        )


class SystemOverloadError(WebSocketError):
    """Erros de sobrecarga do sistema"""
    
    def __init__(self, message: str, current_load: Optional[float] = None, 
                 max_connections: Optional[int] = None, connection_id: Optional[str] = None, **kwargs):
        details = {}
        if current_load is not None:
            details["current_load"] = current_load
        if max_connections is not None:
            details["max_connections"] = max_connections
            
        super().__init__(
            message=message,
            error_code="SYSTEM_OVERLOAD",
            severity=ErrorSeverity.HIGH,
            connection_id=connection_id,
            details=details,
            recoverable=False,  # Sistema sobrecarregado não é recuperável automaticamente
            **kwargs
        )


class SecurityError(WebSocketError):
    """Erros relacionados à segurança"""
    
    def __init__(self, message: str, security_violation: Optional[str] = None, 
                 connection_id: Optional[str] = None, **kwargs):
        details = {}
        if security_violation:
            details["security_violation"] = security_violation
            
        super().__init__(
            message=message,
            error_code="SECURITY_ERROR",
            severity=ErrorSeverity.CRITICAL,
            connection_id=connection_id,
            details=details,
            recoverable=False,  # Erros de segurança não são recuperáveis
            **kwargs
        )


class ConfigurationError(WebSocketError):
    """Erros de configuração"""
    
    def __init__(self, message: str, config_key: Optional[str] = None, 
                 config_value: Optional[str] = None, **kwargs):
        details = {}
        if config_key:
            details["config_key"] = config_key
        if config_value:
            details["config_value"] = config_value
            
        super().__init__(
            message=message,
            error_code="CONFIGURATION_ERROR",
            severity=ErrorSeverity.HIGH,
            details=details,
            recoverable=False,
            **kwargs
        )


class SessionNotFoundError(WebSocketError):
    """Erro quando uma sessão não é encontrada"""
    
    def __init__(self, message: str, session_id: Optional[str] = None, **kwargs):
        details = {}
        if session_id:
            details["session_id"] = session_id
            
        super().__init__(
            message=message,
            error_code="SESSION_NOT_FOUND",
            severity=ErrorSeverity.MEDIUM,
            details=details,
            recoverable=True,
            **kwargs
        )


class SessionCreationError(WebSocketError):
    """Erro durante criação de sessão"""
    
    def __init__(self, message: str, session_id: Optional[str] = None, **kwargs):
        details = {}
        if session_id:
            details["session_id"] = session_id
            
        super().__init__(
            message=message,
            error_code="SESSION_CREATION_ERROR",
            severity=ErrorSeverity.HIGH,
            details=details,
            recoverable=True,
            **kwargs
        )


class IntegrationError(WebSocketError):
    """Erros de integração entre componentes"""
    
    def __init__(self, message: str, component: Optional[str] = None, **kwargs):
        details = {}
        if component:
            details["component"] = component
            
        super().__init__(
            message=message,
            error_code="INTEGRATION_ERROR",
            severity=ErrorSeverity.CRITICAL,
            details=details,
            recoverable=False,
            **kwargs
        )


# Mapeamento de tipos de erro para facilitar a criação automática
ERROR_TYPE_MAPPING = {
    "connection": ConnectionError,
    "parsing": MessageParsingError,
    "audio": AudioProcessingError,
    "broadcast": BroadcastError,
    "protocol": ProtocolViolationError,
    "rate_limit": RateLimitError,
    "overload": SystemOverloadError,
    "security": SecurityError,
    "config": ConfigurationError,
}


def create_error(error_type: str, message: str, **kwargs) -> WebSocketError:
    """
    Factory function para criar erros específicos.
    
    Args:
        error_type: Tipo do erro (chave do ERROR_TYPE_MAPPING)
        message: Mensagem do erro
        **kwargs: Argumentos adicionais específicos do tipo de erro
        
    Returns:
        WebSocketError: Instância da exceção apropriada
    """
    error_class = ERROR_TYPE_MAPPING.get(error_type, WebSocketError)
    return error_class(message, **kwargs) 