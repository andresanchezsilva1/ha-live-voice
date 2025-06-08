"""
Sistema de monitoramento de performance para WebSocket.
Coleta e armazena métricas em tempo real para análise e otimização.
"""

import time
import asyncio
import logging
from typing import Dict, Any, Optional, List, Deque
from datetime import datetime, timedelta
from collections import deque, defaultdict
from dataclasses import dataclass, field
from enum import Enum
import threading
import json

logger = logging.getLogger(__name__)


class MetricType(str, Enum):
    """Tipos de métricas coletadas"""
    CONNECTION = "connection"
    MESSAGE = "message"
    ERROR = "error"
    PERFORMANCE = "performance"
    SYSTEM = "system"


@dataclass
class MetricPoint:
    """Ponto individual de métrica"""
    timestamp: datetime
    metric_type: MetricType
    name: str
    value: float
    tags: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConnectionMetrics:
    """Métricas específicas de uma conexão"""
    connection_id: str
    connected_at: datetime
    total_messages: int = 0
    total_bytes_sent: int = 0
    total_bytes_received: int = 0
    last_activity: datetime = field(default_factory=datetime.utcnow)
    error_count: int = 0
    average_response_time: float = 0.0
    response_times: Deque[float] = field(default_factory=lambda: deque(maxlen=100))


class PerformanceMonitor:
    """
    Monitor de performance em tempo real para WebSocket.
    Coleta métricas de conexão, mensagens, erros e sistema.
    """
    
    def __init__(self, max_metric_points: int = 10000, retention_hours: int = 24):
        self.max_metric_points = max_metric_points
        self.retention_hours = retention_hours
        
        # Armazenamento de métricas
        self.metrics: Deque[MetricPoint] = deque(maxlen=max_metric_points)
        self.connection_metrics: Dict[str, ConnectionMetrics] = {}
        
        # Contadores e agregações
        self.counters = defaultdict(int)
        self.gauges = defaultdict(float)
        self.timers = defaultdict(list)
        
        # Sistema de coleta contínua
        self._monitoring_active = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._lock = threading.Lock()
        
        # Estatísticas em tempo real
        self.start_time = datetime.utcnow()
        self.last_cleanup = datetime.utcnow()
    
    def start_monitoring(self) -> None:
        """Inicia o monitoramento contínuo"""
        if not self._monitoring_active:
            self._monitoring_active = True
            self._monitor_task = asyncio.create_task(self._continuous_monitoring())
            logger.info("Sistema de monitoramento de performance iniciado")
    
    def stop_monitoring(self) -> None:
        """Para o monitoramento contínuo"""
        self._monitoring_active = False
        if self._monitor_task:
            self._monitor_task.cancel()
        logger.info("Sistema de monitoramento de performance parado")
    
    async def _continuous_monitoring(self) -> None:
        """Loop de monitoramento contínuo"""
        while self._monitoring_active:
            try:
                await self._collect_system_metrics()
                await self._cleanup_old_metrics()
                await asyncio.sleep(30)  # Coleta a cada 30 segundos
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erro no monitoramento contínuo: {e}")
                await asyncio.sleep(5)
    
    async def _collect_system_metrics(self) -> None:
        """Coleta métricas do sistema"""
        try:
            import psutil
            
            # CPU e memória
            cpu_percent = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            
            self.record_gauge("system.cpu_percent", cpu_percent)
            self.record_gauge("system.memory_percent", memory.percent)
            self.record_gauge("system.memory_available", memory.available / (1024**3))  # GB
            
        except ImportError:
            # psutil não disponível, usar métricas básicas
            pass
        
        # Métricas internas
        self.record_gauge("websocket.active_connections", len(self.connection_metrics))
        self.record_gauge("metrics.total_points", len(self.metrics))
    
    async def _cleanup_old_metrics(self) -> None:
        """Remove métricas antigas para economizar memória"""
        now = datetime.utcnow()
        if now - self.last_cleanup < timedelta(hours=1):
            return
        
        cutoff_time = now - timedelta(hours=self.retention_hours)
        
        with self._lock:
            # Limpar métricas antigas
            while self.metrics and self.metrics[0].timestamp < cutoff_time:
                self.metrics.popleft()
            
            # Limpar conexões inativas antigas
            inactive_connections = [
                conn_id for conn_id, metrics in self.connection_metrics.items()
                if metrics.last_activity < cutoff_time
            ]
            
            for conn_id in inactive_connections:
                del self.connection_metrics[conn_id]
        
        self.last_cleanup = now
        logger.debug(f"Limpeza de métricas: {len(inactive_connections)} conexões removidas")
    
    def record_connection_start(self, connection_id: str) -> None:
        """Registra início de uma nova conexão"""
        with self._lock:
            self.connection_metrics[connection_id] = ConnectionMetrics(
                connection_id=connection_id,
                connected_at=datetime.utcnow()
            )
        
        self.record_counter("connections.started")
        self.record_metric(MetricType.CONNECTION, "connection.started", 1, 
                          tags={"connection_id": connection_id})
    
    def record_connection_end(self, connection_id: str) -> None:
        """Registra fim de uma conexão"""
        with self._lock:
            if connection_id in self.connection_metrics:
                conn_metrics = self.connection_metrics[connection_id]
                duration = (datetime.utcnow() - conn_metrics.connected_at).total_seconds()
                
                self.record_metric(MetricType.CONNECTION, "connection.duration", duration,
                                 tags={"connection_id": connection_id})
                
                # Manter métricas por mais tempo antes de remover
                # del self.connection_metrics[connection_id]
        
        self.record_counter("connections.ended")
        self.record_metric(MetricType.CONNECTION, "connection.ended", 1,
                          tags={"connection_id": connection_id})
    
    def record_message_sent(self, connection_id: str, message_type: str, 
                           size_bytes: int, processing_time: Optional[float] = None) -> None:
        """Registra envio de mensagem"""
        with self._lock:
            if connection_id in self.connection_metrics:
                conn_metrics = self.connection_metrics[connection_id]
                conn_metrics.total_messages += 1
                conn_metrics.total_bytes_sent += size_bytes
                conn_metrics.last_activity = datetime.utcnow()
                
                if processing_time is not None:
                    conn_metrics.response_times.append(processing_time)
                    conn_metrics.average_response_time = sum(conn_metrics.response_times) / len(conn_metrics.response_times)
        
        self.record_counter("messages.sent")
        self.record_counter(f"messages.sent.{message_type}")
        self.record_gauge("messages.size_bytes", size_bytes)
        
        if processing_time is not None:
            self.record_timer("messages.processing_time", processing_time)
        
        self.record_metric(MetricType.MESSAGE, "message.sent", 1,
                          tags={"connection_id": connection_id, "type": message_type},
                          metadata={"size_bytes": size_bytes, "processing_time": processing_time})
    
    def record_message_received(self, connection_id: str, message_type: str, size_bytes: int) -> None:
        """Registra recebimento de mensagem"""
        with self._lock:
            if connection_id in self.connection_metrics:
                conn_metrics = self.connection_metrics[connection_id]
                conn_metrics.total_bytes_received += size_bytes
                conn_metrics.last_activity = datetime.utcnow()
        
        self.record_counter("messages.received")
        self.record_counter(f"messages.received.{message_type}")
        
        self.record_metric(MetricType.MESSAGE, "message.received", 1,
                          tags={"connection_id": connection_id, "type": message_type},
                          metadata={"size_bytes": size_bytes})
    
    def record_error(self, connection_id: Optional[str], error_type: str, 
                    error_code: str, severity: str) -> None:
        """Registra ocorrência de erro"""
        if connection_id:
            with self._lock:
                if connection_id in self.connection_metrics:
                    self.connection_metrics[connection_id].error_count += 1
        
        self.record_counter("errors.total")
        self.record_counter(f"errors.{error_type}")
        self.record_counter(f"errors.severity.{severity}")
        
        tags = {"error_type": error_type, "error_code": error_code, "severity": severity}
        if connection_id:
            tags["connection_id"] = connection_id
        
        self.record_metric(MetricType.ERROR, "error.occurred", 1, tags=tags)
    
    def record_counter(self, name: str, value: int = 1) -> None:
        """Registra um contador"""
        with self._lock:
            self.counters[name] += value
    
    def record_gauge(self, name: str, value: float) -> None:
        """Registra um gauge (valor instantâneo)"""
        with self._lock:
            self.gauges[name] = value
    
    def record_timer(self, name: str, value: float) -> None:
        """Registra um timer"""
        with self._lock:
            self.timers[name].append(value)
            # Manter apenas os últimos 1000 valores
            if len(self.timers[name]) > 1000:
                self.timers[name] = self.timers[name][-1000:]
    
    def record_metric(self, metric_type: MetricType, name: str, value: float,
                     tags: Optional[Dict[str, str]] = None,
                     metadata: Optional[Dict[str, Any]] = None) -> None:
        """Registra um ponto de métrica genérico"""
        point = MetricPoint(
            timestamp=datetime.utcnow(),
            metric_type=metric_type,
            name=name,
            value=value,
            tags=tags or {},
            metadata=metadata or {}
        )
        
        with self._lock:
            self.metrics.append(point)
    
    def get_connection_metrics(self, connection_id: str) -> Optional[ConnectionMetrics]:
        """Retorna métricas de uma conexão específica"""
        with self._lock:
            return self.connection_metrics.get(connection_id)
    
    def get_all_connection_metrics(self) -> Dict[str, ConnectionMetrics]:
        """Retorna métricas de todas as conexões"""
        with self._lock:
            return dict(self.connection_metrics)
    
    def get_system_summary(self) -> Dict[str, Any]:
        """Retorna resumo do sistema"""
        now = datetime.utcnow()
        uptime = (now - self.start_time).total_seconds()
        
        # Calcular estatísticas de timer
        timer_stats = {}
        for name, values in self.timers.items():
            if values:
                timer_stats[name] = {
                    "count": len(values),
                    "avg": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                    "p95": sorted(values)[int(len(values) * 0.95)] if len(values) > 10 else max(values)
                }
        
        # Métricas de conexão
        active_connections = len(self.connection_metrics)
        total_messages = sum(conn.total_messages for conn in self.connection_metrics.values())
        total_errors = sum(conn.error_count for conn in self.connection_metrics.values())
        
        return {
            "timestamp": now.isoformat(),
            "uptime_seconds": uptime,
            "system": {
                "active_connections": active_connections,
                "total_metrics_points": len(self.metrics),
                "total_messages_processed": total_messages,
                "total_errors": total_errors,
                "messages_per_second": total_messages / uptime if uptime > 0 else 0
            },
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
            "timers": timer_stats,
            "connections": {
                conn_id: {
                    "connected_at": conn.connected_at.isoformat(),
                    "total_messages": conn.total_messages,
                    "total_bytes_sent": conn.total_bytes_sent,
                    "total_bytes_received": conn.total_bytes_received,
                    "error_count": conn.error_count,
                    "average_response_time": conn.average_response_time,
                    "last_activity": conn.last_activity.isoformat()
                }
                for conn_id, conn in self.connection_metrics.items()
            }
        }
    
    def get_metrics_by_type(self, metric_type: MetricType, 
                           minutes: int = 60) -> List[MetricPoint]:
        """Retorna métricas de um tipo específico"""
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
        
        with self._lock:
            return [
                metric for metric in self.metrics
                if metric.metric_type == metric_type and metric.timestamp >= cutoff_time
            ]
    
    def get_recent_metrics(self, minutes: int = 60) -> List[MetricPoint]:
        """Retorna métricas recentes"""
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
        
        with self._lock:
            return [
                metric for metric in self.metrics
                if metric.timestamp >= cutoff_time
            ]
    
    def export_metrics(self, format_type: str = "json") -> str:
        """Exporta métricas em formato específico"""
        if format_type == "json":
            return json.dumps(self.get_system_summary(), indent=2, default=str)
        elif format_type == "prometheus":
            # Formato Prometheus simples
            lines = []
            for name, value in self.counters.items():
                lines.append(f"websocket_{name.replace('.', '_')}_total {value}")
            for name, value in self.gauges.items():
                lines.append(f"websocket_{name.replace('.', '_')} {value}")
            return "\n".join(lines)
        else:
            raise ValueError(f"Formato não suportado: {format_type}")
    
    def reset_metrics(self) -> None:
        """Reset de todas as métricas (útil para testes)"""
        with self._lock:
            self.metrics.clear()
            self.connection_metrics.clear()
            self.counters.clear()
            self.gauges.clear()
            self.timers.clear()
        
        self.start_time = datetime.utcnow()
        logger.info("Métricas resetadas")


# Instância global do monitor
performance_monitor = PerformanceMonitor() 