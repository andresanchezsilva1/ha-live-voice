"""
Sistema de logging estruturado para WebSocket.
Implementa formatação JSON, contexto enriquecido e diferentes níveis de logging.
"""

import logging
import json
import traceback
from typing import Dict, Any, Optional
from datetime import datetime
from contextvars import ContextVar
from functools import wraps
import sys
import os

# Context variables para rastreamento de contexto através de calls assíncronos
connection_context: ContextVar[Optional[str]] = ContextVar('connection_id', default=None)
request_context: ContextVar[Optional[str]] = ContextVar('request_id', default=None)
operation_context: ContextVar[Optional[str]] = ContextVar('operation', default=None)


class StructuredFormatter(logging.Formatter):
    """Formatter personalizado para logs estruturados em JSON"""
    
    def __init__(self, include_extra: bool = True):
        super().__init__()
        self.include_extra = include_extra
    
    def format(self, record: logging.LogRecord) -> str:
        """Formata o log record em JSON estruturado"""
        
        # Dados básicos do log
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Adicionar contexto se disponível
        if connection_context.get():
            log_data["connection_id"] = connection_context.get()
        if request_context.get():
            log_data["request_id"] = request_context.get()
        if operation_context.get():
            log_data["operation"] = operation_context.get()
        
        # Adicionar informações de exceção se presente
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info)
            }
        
        # Adicionar campos extras
        if self.include_extra:
            for key, value in record.__dict__.items():
                if key not in ['name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 
                              'filename', 'module', 'lineno', 'funcName', 'created', 'msecs',
                              'relativeCreated', 'thread', 'threadName', 'processName', 
                              'process', 'message', 'exc_info', 'exc_text', 'stack_info']:
                    log_data[key] = value
        
        return json.dumps(log_data, default=str, ensure_ascii=False)


class WebSocketLogger:
    """
    Logger especializado para operações WebSocket com contexto e métricas.
    """
    
    def __init__(self, name: str, level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        
        # Configurar handler se não existe
        if not self.logger.handlers:
            self._setup_handlers()
    
    def _setup_handlers(self) -> None:
        """Configura handlers para console e arquivo"""
        
        # Handler para console (desenvolvimento)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        
        # Usar formatter simples em desenvolvimento, JSON em produção
        if os.getenv("ENVIRONMENT") == "production":
            console_formatter = StructuredFormatter()
        else:
            console_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # Handler para arquivo (sempre JSON estruturado)
        try:
            file_handler = logging.FileHandler('logs/websocket.log')
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(StructuredFormatter())
            self.logger.addHandler(file_handler)
        except (FileNotFoundError, PermissionError):
            # Ignorar se não conseguir criar arquivo de log
            pass
    
    def with_connection(self, connection_id: str):
        """Context manager para definir connection_id no contexto"""
        class ConnectionContext:
            def __enter__(self):
                connection_context.set(connection_id)
                return self
            
            def __exit__(self, exc_type, exc_val, exc_tb):
                connection_context.set(None)
        
        return ConnectionContext()
    
    def with_operation(self, operation: str):
        """Context manager para definir operação no contexto"""
        class OperationContext:
            def __enter__(self):
                operation_context.set(operation)
                return self
            
            def __exit__(self, exc_type, exc_val, exc_tb):
                operation_context.set(None)
        
        return OperationContext()
    
    def connection_started(self, connection_id: str, remote_addr: Optional[str] = None, 
                          user_agent: Optional[str] = None, **kwargs) -> None:
        """Log específico para início de conexão"""
        extra = {
            "event_type": "connection_started",
            "connection_id": connection_id,
            "remote_addr": remote_addr,
            "user_agent": user_agent,
            **kwargs
        }
        
        with self.with_connection(connection_id):
            self.logger.info(f"Nova conexão WebSocket estabelecida", extra=extra)
    
    def connection_ended(self, connection_id: str, duration_seconds: Optional[float] = None,
                        reason: Optional[str] = None, **kwargs) -> None:
        """Log específico para fim de conexão"""
        extra = {
            "event_type": "connection_ended",
            "connection_id": connection_id,
            "duration_seconds": duration_seconds,
            "reason": reason,
            **kwargs
        }
        
        with self.with_connection(connection_id):
            self.logger.info(f"Conexão WebSocket encerrada", extra=extra)
    
    def message_received(self, connection_id: str, message_type: str, 
                        size_bytes: int, **kwargs) -> None:
        """Log específico para mensagem recebida"""
        extra = {
            "event_type": "message_received",
            "connection_id": connection_id,
            "message_type": message_type,
            "size_bytes": size_bytes,
            **kwargs
        }
        
        with self.with_connection(connection_id):
            with self.with_operation("message_processing"):
                self.logger.debug(f"Mensagem recebida: {message_type}", extra=extra)
    
    def message_sent(self, connection_id: str, message_type: str, size_bytes: int,
                    processing_time_ms: Optional[float] = None, **kwargs) -> None:
        """Log específico para mensagem enviada"""
        extra = {
            "event_type": "message_sent",
            "connection_id": connection_id,
            "message_type": message_type,
            "size_bytes": size_bytes,
            "processing_time_ms": processing_time_ms,
            **kwargs
        }
        
        with self.with_connection(connection_id):
            with self.with_operation("message_response"):
                self.logger.debug(f"Mensagem enviada: {message_type}", extra=extra)
    
    def error_occurred(self, connection_id: Optional[str], error_type: str, 
                      error_code: str, error_message: str, severity: str,
                      **kwargs) -> None:
        """Log específico para erros"""
        extra = {
            "event_type": "error_occurred",
            "connection_id": connection_id,
            "error_type": error_type,
            "error_code": error_code,
            "severity": severity,
            **kwargs
        }
        
        log_method = getattr(self.logger, severity.lower(), self.logger.error)
        
        if connection_id:
            with self.with_connection(connection_id):
                log_method(f"Erro WebSocket: {error_message}", extra=extra)
        else:
            log_method(f"Erro WebSocket: {error_message}", extra=extra)
    
    def broadcast_sent(self, sender_id: str, recipients_count: int, 
                      failed_count: int = 0, **kwargs) -> None:
        """Log específico para broadcast"""
        extra = {
            "event_type": "broadcast_sent",
            "sender_id": sender_id,
            "recipients_count": recipients_count,
            "failed_count": failed_count,
            "success_rate": (recipients_count / (recipients_count + failed_count)) if (recipients_count + failed_count) > 0 else 0,
            **kwargs
        }
        
        with self.with_connection(sender_id):
            with self.with_operation("broadcast"):
                self.logger.info(f"Broadcast enviado para {recipients_count} conexões", extra=extra)
    
    def performance_metric(self, metric_name: str, value: float, unit: str = "",
                          tags: Optional[Dict[str, str]] = None, **kwargs) -> None:
        """Log específico para métricas de performance"""
        extra = {
            "event_type": "performance_metric",
            "metric_name": metric_name,
            "value": value,
            "unit": unit,
            "tags": tags or {},
            **kwargs
        }
        
        self.logger.debug(f"Métrica: {metric_name} = {value} {unit}", extra=extra)
    
    def circuit_breaker_event(self, event: str, state: str, failure_count: int = 0,
                             **kwargs) -> None:
        """Log específico para eventos do circuit breaker"""
        extra = {
            "event_type": "circuit_breaker_event",
            "circuit_event": event,
            "circuit_state": state,
            "failure_count": failure_count,
            **kwargs
        }
        
        with self.with_operation("circuit_breaker"):
            if event in ["opened", "critical"]:
                self.logger.error(f"Circuit breaker {event}: {state}", extra=extra)
            else:
                self.logger.info(f"Circuit breaker {event}: {state}", extra=extra)
    
    def system_event(self, event: str, message: str, **kwargs) -> None:
        """Log genérico para eventos do sistema"""
        extra = {
            "event_type": "system_event",
            "system_event": event,
            **kwargs
        }
        
        with self.with_operation("system"):
            self.logger.info(f"Sistema: {message}", extra=extra)
    
    def debug(self, message: str, **kwargs) -> None:
        """Log de debug com contexto"""
        self.logger.debug(message, extra=kwargs)
    
    def info(self, message: str, **kwargs) -> None:
        """Log de info com contexto"""
        self.logger.info(message, extra=kwargs)
    
    def warning(self, message: str, **kwargs) -> None:
        """Log de warning com contexto"""
        self.logger.warning(message, extra=kwargs)
    
    def error(self, message: str, **kwargs) -> None:
        """Log de error com contexto"""
        self.logger.error(message, extra=kwargs)
    
    def critical(self, message: str, **kwargs) -> None:
        """Log de critical com contexto"""
        self.logger.critical(message, extra=kwargs)


def log_async_operation(operation_name: str):
    """Decorator para logar operações assíncronas automaticamente"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = datetime.utcnow()
            logger = WebSocketLogger(func.__module__)
            
            with logger.with_operation(operation_name):
                try:
                    logger.debug(f"Iniciando operação: {operation_name}")
                    result = await func(*args, **kwargs)
                    
                    duration = (datetime.utcnow() - start_time).total_seconds() * 1000
                    logger.performance_metric(
                        f"operation.{operation_name}.duration",
                        duration,
                        "ms",
                        tags={"status": "success"}
                    )
                    
                    return result
                
                except Exception as e:
                    duration = (datetime.utcnow() - start_time).total_seconds() * 1000
                    logger.performance_metric(
                        f"operation.{operation_name}.duration",
                        duration,
                        "ms",
                        tags={"status": "error"}
                    )
                    
                    logger.error(
                        f"Erro na operação {operation_name}: {str(e)}",
                        error_type=type(e).__name__,
                        operation=operation_name
                    )
                    raise
        
        return wrapper
    return decorator


def setup_logging(level: str = "INFO", log_dir: str = "logs") -> None:
    """Configura o sistema de logging global"""
    
    # Criar diretório de logs se não existir
    os.makedirs(log_dir, exist_ok=True)
    
    # Configurar nível de logging
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.getLogger().setLevel(numeric_level)
    
    # Configurar logger raiz com formato estruturado
    root_logger = logging.getLogger()
    
    # Remover handlers existentes
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Handler para console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    
    if os.getenv("ENVIRONMENT") == "production":
        console_formatter = StructuredFormatter()
    else:
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # Handler para arquivo principal
    try:
        file_handler = logging.FileHandler(os.path.join(log_dir, 'app.log'))
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(StructuredFormatter())
        root_logger.addHandler(file_handler)
    except (FileNotFoundError, PermissionError):
        pass


# Instância global do logger WebSocket
websocket_logger = WebSocketLogger("websocket") 