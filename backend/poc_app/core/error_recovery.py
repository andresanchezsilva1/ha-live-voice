"""
Sistema de recuperação de erros para WebSocket.
Implementa padrões como Circuit Breaker, Retry Logic e Health Monitoring.
"""

import asyncio
import logging
from typing import Dict, Optional, Callable, Any, List
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
from collections import deque

from .exceptions import WebSocketError, ErrorSeverity

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """Estados do Circuit Breaker"""
    CLOSED = "closed"        # Funcionando normalmente
    OPEN = "open"           # Circuito aberto, rejeitando requisições
    HALF_OPEN = "half_open"  # Testando se pode voltar ao normal


@dataclass
class RetryConfig:
    """Configuração de retry para diferentes tipos de erro"""
    max_attempts: int = 3
    initial_delay: float = 1.0
    max_delay: float = 60.0
    backoff_factor: float = 2.0
    jitter: bool = True


@dataclass
class CircuitBreakerConfig:
    """Configuração do Circuit Breaker"""
    failure_threshold: int = 5      # Número de falhas para abrir o circuito
    recovery_timeout: float = 30.0  # Tempo para tentar fechar o circuito
    half_open_max_calls: int = 3    # Máximo de chamadas em half-open


@dataclass
class ErrorRecord:
    """Registro de um erro ocorrido"""
    timestamp: datetime
    error_type: str
    error_code: str
    severity: ErrorSeverity
    connection_id: Optional[str]
    recoverable: bool
    recovery_attempted: bool = False


class HealthStatus(str, Enum):
    """Status de saúde do sistema"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"


class ErrorRecoveryManager:
    """
    Gerenciador de recuperação de erros com Circuit Breaker e Retry Logic.
    """
    
    def __init__(self, 
                 retry_config: Optional[RetryConfig] = None,
                 circuit_config: Optional[CircuitBreakerConfig] = None,
                 max_error_history: int = 1000):
        
        self.retry_config = retry_config or RetryConfig()
        self.circuit_config = circuit_config or CircuitBreakerConfig()
        self.max_error_history = max_error_history
        
        # Estado do Circuit Breaker
        self.circuit_state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.half_open_calls = 0
        
        # Histórico de erros
        self.error_history: deque = deque(maxlen=max_error_history)
        self.error_stats: Dict[str, int] = {}
        
        # Callbacks para notificações
        self.on_circuit_opened: Optional[Callable] = None
        self.on_circuit_closed: Optional[Callable] = None
        self.on_critical_error: Optional[Callable] = None
    
    async def execute_with_recovery(self, 
                                  operation: Callable,
                                  connection_id: Optional[str] = None,
                                  error_context: Optional[Dict[str, Any]] = None) -> Any:
        """
        Executa uma operação com recuperação automática de erros.
        
        Args:
            operation: Função a ser executada
            connection_id: ID da conexão (para logging)
            error_context: Contexto adicional para tratamento de erros
            
        Returns:
            Any: Resultado da operação
            
        Raises:
            WebSocketError: Se a operação falhar após todas as tentativas
        """
        # Verificar circuit breaker
        if not self._can_execute():
            raise WebSocketError(
                "Circuit breaker aberto - sistema em recuperação",
                error_code="CIRCUIT_BREAKER_OPEN",
                severity=ErrorSeverity.HIGH,
                connection_id=connection_id
            )
        
        last_error = None
        
        for attempt in range(self.retry_config.max_attempts):
            try:
                result = await operation()
                
                # Sucesso - resetar circuit breaker se estava em half-open
                if self.circuit_state == CircuitState.HALF_OPEN:
                    self._close_circuit()
                
                return result
                
            except Exception as e:
                last_error = e
                
                # Converter para WebSocketError se necessário
                if not isinstance(e, WebSocketError):
                    websocket_error = WebSocketError(
                        message=str(e),
                        connection_id=connection_id,
                        details=error_context or {}
                    )
                else:
                    websocket_error = e
                
                # Registrar erro
                self._record_error(websocket_error)
                
                # Verificar se deve tentar novamente
                if not websocket_error.recoverable or attempt == self.retry_config.max_attempts - 1:
                    self._handle_failure()
                    raise websocket_error
                
                # Calcular delay para retry
                delay = self._calculate_retry_delay(attempt)
                logger.warning(
                    f"Tentativa {attempt + 1} falhou, tentando novamente em {delay:.2f}s: {websocket_error.message}"
                )
                
                await asyncio.sleep(delay)
        
        # Se chegou aqui, esgotou todas as tentativas
        self._handle_failure()
        raise last_error
    
    def _can_execute(self) -> bool:
        """Verifica se o circuit breaker permite execução"""
        now = datetime.utcnow()
        
        if self.circuit_state == CircuitState.CLOSED:
            return True
        elif self.circuit_state == CircuitState.OPEN:
            # Verificar se é hora de tentar half-open
            if (self.last_failure_time and 
                now - self.last_failure_time >= timedelta(seconds=self.circuit_config.recovery_timeout)):
                self.circuit_state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                logger.info("Circuit breaker mudou para HALF_OPEN")
                return True
            return False
        else:  # HALF_OPEN
            if self.half_open_calls < self.circuit_config.half_open_max_calls:
                self.half_open_calls += 1
                return True
            return False
    
    def _handle_failure(self) -> None:
        """Trata uma falha incrementando contadores e atualizando circuit breaker"""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        
        if self.circuit_state == CircuitState.HALF_OPEN:
            # Voltar para OPEN se falhar em half-open
            self.circuit_state = CircuitState.OPEN
            self.failure_count = 0  # Reset para próxima tentativa de recovery
            logger.warning("Circuit breaker voltou para OPEN após falha em HALF_OPEN")
            if self.on_circuit_opened:
                asyncio.create_task(self.on_circuit_opened())
        
        elif (self.circuit_state == CircuitState.CLOSED and 
              self.failure_count >= self.circuit_config.failure_threshold):
            # Abrir circuit breaker
            self.circuit_state = CircuitState.OPEN
            logger.error(f"Circuit breaker ABERTO após {self.failure_count} falhas")
            if self.on_circuit_opened:
                asyncio.create_task(self.on_circuit_opened())
    
    def _close_circuit(self) -> None:
        """Fecha o circuit breaker após sucesso"""
        if self.circuit_state != CircuitState.CLOSED:
            self.circuit_state = CircuitState.CLOSED
            self.failure_count = 0
            self.half_open_calls = 0
            logger.info("Circuit breaker FECHADO - sistema recuperado")
            if self.on_circuit_closed:
                asyncio.create_task(self.on_circuit_closed())
    
    def _calculate_retry_delay(self, attempt: int) -> float:
        """Calcula delay para retry com exponential backoff"""
        delay = min(
            self.retry_config.initial_delay * (self.retry_config.backoff_factor ** attempt),
            self.retry_config.max_delay
        )
        
        # Adicionar jitter para evitar thundering herd
        if self.retry_config.jitter:
            import random
            delay *= (0.5 + random.random() * 0.5)  # ±50% jitter
        
        return delay
    
    def _record_error(self, error: WebSocketError) -> None:
        """Registra um erro no histórico"""
        record = ErrorRecord(
            timestamp=datetime.utcnow(),
            error_type=type(error).__name__,
            error_code=error.error_code,
            severity=error.severity,
            connection_id=error.connection_id,
            recoverable=error.recoverable
        )
        
        self.error_history.append(record)
        
        # Atualizar estatísticas
        self.error_stats[error.error_code] = self.error_stats.get(error.error_code, 0) + 1
        
        # Notificar erros críticos
        if error.severity == ErrorSeverity.CRITICAL and self.on_critical_error:
            asyncio.create_task(self.on_critical_error(error))
    
    def get_health_status(self) -> HealthStatus:
        """Calcula status de saúde baseado no estado atual"""
        if self.circuit_state == CircuitState.OPEN:
            return HealthStatus.CRITICAL
        elif self.circuit_state == CircuitState.HALF_OPEN:
            return HealthStatus.DEGRADED
        
        # Análise baseada em erros recentes
        recent_errors = self._get_recent_errors(minutes=5)
        if len(recent_errors) == 0:
            return HealthStatus.HEALTHY
        
        critical_errors = sum(1 for e in recent_errors if e.severity == ErrorSeverity.CRITICAL)
        high_errors = sum(1 for e in recent_errors if e.severity == ErrorSeverity.HIGH)
        
        if critical_errors > 0:
            return HealthStatus.CRITICAL
        elif high_errors > 3:
            return HealthStatus.UNHEALTHY
        elif len(recent_errors) > 10:
            return HealthStatus.DEGRADED
        else:
            return HealthStatus.HEALTHY
    
    def _get_recent_errors(self, minutes: int = 5) -> List[ErrorRecord]:
        """Retorna erros ocorridos nos últimos X minutos"""
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
        return [error for error in self.error_history if error.timestamp >= cutoff_time]
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """Retorna estatísticas detalhadas de erros"""
        recent_errors = self._get_recent_errors()
        
        return {
            "circuit_breaker": {
                "state": self.circuit_state.value,
                "failure_count": self.failure_count,
                "last_failure": self.last_failure_time.isoformat() if self.last_failure_time else None
            },
            "health_status": self.get_health_status().value,
            "error_counts": dict(self.error_stats),
            "recent_errors": {
                "total": len(recent_errors),
                "by_severity": {
                    severity.value: sum(1 for e in recent_errors if e.severity == severity)
                    for severity in ErrorSeverity
                },
                "by_type": {}
            },
            "total_errors": len(self.error_history)
        }
    
    def reset_circuit_breaker(self) -> None:
        """Reset manual do circuit breaker (para admin)"""
        self.circuit_state = CircuitState.CLOSED
        self.failure_count = 0
        self.half_open_calls = 0
        self.last_failure_time = None
        logger.info("Circuit breaker resetado manualmente")
    
    def set_callbacks(self, 
                     on_circuit_opened: Optional[Callable] = None,
                     on_circuit_closed: Optional[Callable] = None,
                     on_critical_error: Optional[Callable] = None) -> None:
        """Define callbacks para notificações de eventos"""
        self.on_circuit_opened = on_circuit_opened
        self.on_circuit_closed = on_circuit_closed
        self.on_critical_error = on_critical_error 