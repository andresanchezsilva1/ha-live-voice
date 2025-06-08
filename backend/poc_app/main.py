# backend/poc_app/main.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from .core.config import settings
from .core.websocket_handler import WebSocketHandler
from .core.message_protocol import MessageProtocol
from .core.error_recovery import HealthStatus
from .core.performance_monitor import performance_monitor, MetricType
from .core.structured_logger import websocket_logger, setup_logging
import logging
import uvicorn
from datetime import datetime, timedelta
from typing import Optional

# Configurar sistema de logging estruturado
setup_logging(level=settings.LOG_LEVEL, log_dir="logs")

# Configurar logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Criar aplicação FastAPI
app = FastAPI(
    title="Home Assistant Voice Control POC",
    description="POC para controle do Home Assistant com Gemini Live API e interface Vue3",
    version="0.1.0",
    debug=settings.DEBUG
)

# Configurar CORS para permitir conexões do frontend Vue3
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://localhost:8080"],  # URLs típicas do Vue dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instanciar o gerenciador WebSocket
websocket_handler = WebSocketHandler()

@app.on_event("startup")
async def startup_event():
    """Eventos de inicialização da aplicação"""
    websocket_logger.system_event("app_startup", "Aplicação FastAPI iniciada")
    logger.info("Aplicação Home Assistant Voice Control POC iniciada")

@app.on_event("shutdown")
async def shutdown_event():
    """Eventos de encerramento da aplicação"""
    performance_monitor.stop_monitoring()
    websocket_logger.system_event("app_shutdown", "Aplicação FastAPI encerrada")
    logger.info("Aplicação Home Assistant Voice Control POC encerrada")

@app.get("/")
async def root():
    """Endpoint raiz para verificar se a API está funcionando."""
    return {
        "message": "Home Assistant Voice Control POC API",
        "status": "running",
        "version": "0.1.0"
    }


@app.get("/health")
async def health_check():
    """Endpoint de health check para monitoramento."""
    error_recovery = websocket_handler.get_error_recovery()
    health_status = error_recovery.get_health_status()
    
    return {
        "status": health_status.value,
        "system_health": {
            "overall": health_status.value,
            "circuit_breaker": error_recovery.circuit_state.value,
            "active_connections": websocket_handler.get_connection_count()
        },
        "services": {
            "gemini_api_configured": bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "sua_chave_gemini_aqui"),
            "ha_configured": bool(settings.HA_URL and settings.HA_LLAT and settings.HA_LLAT != "seu_token_home_assistant_aqui"),
        },
        "audio_config": {
            "sample_rate": settings.AUDIO_SAMPLE_RATE_GEMINI,
            "channels": settings.AUDIO_CHANNELS_GEMINI
        },
        "websocket_connections": websocket_handler.get_connection_count()
    }


@app.get("/health/detailed")
async def detailed_health_check():
    """
    Endpoint de health check detalhado com informações de diagnóstico.
    Inclui estatísticas de erro, estado do circuit breaker e métricas de performance.
    """
    error_recovery = websocket_handler.get_error_recovery()
    error_stats = error_recovery.get_error_statistics()
    connection_manager = websocket_handler.get_connection_manager()
    
    return {
        "timestamp": websocket_handler._get_current_timestamp(),
        "system_status": {
            "health": error_stats["health_status"],
            "circuit_breaker": error_stats["circuit_breaker"],
            "uptime_status": "operational"  # Poderia calcular uptime real
        },
        "connections": {
            "total_active": connection_manager.get_connection_count(),
            "details": connection_manager.get_all_connections_info()
        },
        "error_analysis": {
            "recent_errors": error_stats["recent_errors"],
            "total_errors": error_stats["total_errors"],
            "error_types": error_stats["error_counts"]
        },
        "performance_metrics": {
            "circuit_state": error_stats["circuit_breaker"]["state"],
            "failure_count": error_stats["circuit_breaker"]["failure_count"],
            "last_failure": error_stats["circuit_breaker"]["last_failure"]
        }
    }


@app.get("/monitoring/dashboard")
async def monitoring_dashboard():
    """
    Endpoint principal do dashboard de monitoramento em tempo real.
    Retorna dados completos de performance, métricas e estatísticas.
    """
    try:
        system_summary = performance_monitor.get_system_summary()
        error_recovery = websocket_handler.get_error_recovery()
        error_stats = error_recovery.get_error_statistics()
        
        return {
            "dashboard_data": {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "refresh_interval": 30,  # segundos
                "performance": system_summary,
                "errors": error_stats,
                "health_status": error_recovery.get_health_status().value,
                "real_time_metrics": {
                    "connections_per_minute": _calculate_connections_per_minute(),
                    "messages_per_minute": _calculate_messages_per_minute(),
                    "error_rate": _calculate_error_rate(),
                    "average_response_time": _calculate_average_response_time()
                }
            }
        }
    except Exception as e:
        logger.error(f"Erro ao gerar dashboard: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@app.get("/monitoring/metrics")
async def get_metrics(
    minutes: int = Query(60, ge=1, le=1440, description="Janela de tempo em minutos"),
    metric_type: Optional[str] = Query(None, description="Filtrar por tipo de métrica"),
    format: str = Query("json", regex="^(json|prometheus)$", description="Formato de saída")
):
    """
    Endpoint para obter métricas filtradas por tempo e tipo.
    Suporta formatos JSON e Prometheus.
    """
    try:
        if format == "prometheus":
            metrics_data = performance_monitor.export_metrics("prometheus")
            return PlainTextResponse(content=metrics_data, media_type="text/plain")
        
        # Filtrar métricas por tipo se especificado
        if metric_type and hasattr(MetricType, metric_type.upper()):
            metric_type_enum = getattr(MetricType, metric_type.upper())
            metrics = performance_monitor.get_metrics_by_type(metric_type_enum, minutes)
        else:
            metrics = performance_monitor.get_recent_metrics(minutes)
        
        # Converter para formato JSON serializável
        metrics_data = [
            {
                "timestamp": metric.timestamp.isoformat(),
                "metric_type": metric.metric_type.value,
                "name": metric.name,
                "value": metric.value,
                "tags": metric.tags,
                "metadata": metric.metadata
            }
            for metric in metrics
        ]
        
        return {
            "metrics": metrics_data,
            "total_count": len(metrics_data),
            "time_window_minutes": minutes,
            "metric_type_filter": metric_type
        }
        
    except Exception as e:
        logger.error(f"Erro ao obter métricas: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@app.get("/monitoring/connections")
async def get_connection_metrics():
    """
    Endpoint para obter métricas detalhadas de todas as conexões.
    Inclui estatísticas por conexão e agregações globais.
    """
    try:
        all_connections = performance_monitor.get_all_connection_metrics()
        
        connection_data = {}
        total_messages = 0
        total_bytes_sent = 0
        total_bytes_received = 0
        total_errors = 0
        
        for conn_id, metrics in all_connections.items():
            connection_data[conn_id] = {
                "connected_at": metrics.connected_at.isoformat(),
                "total_messages": metrics.total_messages,
                "total_bytes_sent": metrics.total_bytes_sent,
                "total_bytes_received": metrics.total_bytes_received,
                "error_count": metrics.error_count,
                "average_response_time": metrics.average_response_time,
                "last_activity": metrics.last_activity.isoformat(),
                "session_duration": (datetime.utcnow() - metrics.connected_at).total_seconds()
            }
            
            total_messages += metrics.total_messages
            total_bytes_sent += metrics.total_bytes_sent
            total_bytes_received += metrics.total_bytes_received
            total_errors += metrics.error_count
        
        return {
            "connections": connection_data,
            "summary": {
                "total_active_connections": len(all_connections),
                "total_messages_processed": total_messages,
                "total_bytes_sent": total_bytes_sent,
                "total_bytes_received": total_bytes_received,
                "total_errors": total_errors,
                "average_messages_per_connection": total_messages / len(all_connections) if all_connections else 0
            },
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
    except Exception as e:
        logger.error(f"Erro ao obter métricas de conexões: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@app.get("/monitoring/errors")
async def get_error_analysis(minutes: int = Query(60, ge=1, le=1440, description="Janela de tempo em minutos")):
    """
    Endpoint para análise detalhada de erros com estatísticas e tendências.
    """
    try:
        error_recovery = websocket_handler.get_error_recovery()
        recent_errors = error_recovery._get_recent_errors(minutes)
        
        # Análise por tipo de erro
        error_by_type = {}
        error_by_severity = {}
        error_timeline = []
        
        for error in recent_errors:
            # Contagem por tipo
            if error.error_type not in error_by_type:
                error_by_type[error.error_type] = {"count": 0, "connections": set()}
            error_by_type[error.error_type]["count"] += 1
            if error.connection_id:
                error_by_type[error.error_type]["connections"].add(error.connection_id)
            
            # Contagem por severidade
            severity = error.severity.value
            error_by_severity[severity] = error_by_severity.get(severity, 0) + 1
            
            # Timeline
            error_timeline.append({
                "timestamp": error.timestamp.isoformat(),
                "error_type": error.error_type,
                "error_code": error.error_code,
                "severity": severity,
                "connection_id": error.connection_id,
                "recoverable": error.recoverable
            })
        
        # Converter sets para listas (para JSON)
        for error_type in error_by_type:
            error_by_type[error_type]["unique_connections"] = len(error_by_type[error_type]["connections"])
            error_by_type[error_type]["connections"] = list(error_by_type[error_type]["connections"])
        
        return {
            "analysis": {
                "time_window_minutes": minutes,
                "total_errors": len(recent_errors),
                "error_rate": len(recent_errors) / minutes if minutes > 0 else 0,
                "by_type": error_by_type,
                "by_severity": error_by_severity,
                "timeline": sorted(error_timeline, key=lambda x: x["timestamp"], reverse=True)
            },
            "circuit_breaker": error_recovery.get_error_statistics()["circuit_breaker"],
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
    except Exception as e:
        logger.error(f"Erro ao analisar erros: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@app.get("/monitoring/performance/realtime")
async def get_realtime_performance():
    """
    Endpoint para métricas de performance em tempo real (últimos 5 minutos).
    Atualizado frequentemente para dashboards ao vivo.
    """
    try:
        recent_metrics = performance_monitor.get_recent_metrics(5)  # últimos 5 minutos
        
        # Calcular métricas em tempo real
        current_connections = websocket_handler.get_connection_count()
        
        # Métricas de mensagens nos últimos 5 minutos
        message_metrics = [m for m in recent_metrics if m.metric_type == MetricType.MESSAGE]
        messages_count = len([m for m in message_metrics if m.name == "message.sent"])
        
        # Métricas de performance
        performance_metrics = [m for m in recent_metrics if m.name.endswith('.duration')]
        avg_response_time = sum(m.value for m in performance_metrics) / len(performance_metrics) if performance_metrics else 0
        
        # Métricas de erro
        error_metrics = [m for m in recent_metrics if m.metric_type == MetricType.ERROR]
        error_count = len(error_metrics)
        
        return {
            "realtime_data": {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "current_connections": current_connections,
                "messages_last_5min": messages_count,
                "average_response_time_ms": avg_response_time,
                "errors_last_5min": error_count,
                "message_rate_per_minute": messages_count,
                "error_rate_percent": (error_count / max(messages_count, 1)) * 100,
                "system_health": websocket_handler.get_error_recovery().get_health_status().value
            },
            "trend_data": {
                "connection_trend": _get_connection_trend(),
                "message_trend": _get_message_trend(),
                "error_trend": _get_error_trend()
            }
        }
        
    except Exception as e:
        logger.error(f"Erro ao obter performance em tempo real: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


def _calculate_connections_per_minute() -> float:
    """Calcula conexões por minuto baseado em métricas recentes"""
    connection_metrics = performance_monitor.get_metrics_by_type(MetricType.CONNECTION, 60)
    start_metrics = [m for m in connection_metrics if m.name == "connection.started"]
    return len(start_metrics)


def _calculate_messages_per_minute() -> float:
    """Calcula mensagens por minuto baseado em métricas recentes"""
    message_metrics = performance_monitor.get_metrics_by_type(MetricType.MESSAGE, 60)
    sent_metrics = [m for m in message_metrics if m.name == "message.sent"]
    return len(sent_metrics)


def _calculate_error_rate() -> float:
    """Calcula taxa de erro como porcentagem"""
    recent_metrics = performance_monitor.get_recent_metrics(60)
    error_count = len([m for m in recent_metrics if m.metric_type == MetricType.ERROR])
    message_count = len([m for m in recent_metrics if m.metric_type == MetricType.MESSAGE])
    
    if message_count == 0:
        return 0.0
    
    return (error_count / message_count) * 100


def _calculate_average_response_time() -> float:
    """Calcula tempo médio de resposta em ms"""
    recent_metrics = performance_monitor.get_recent_metrics(60)
    response_times = [m.value for m in recent_metrics if 'duration' in m.name or 'processing_time' in m.name]
    
    if not response_times:
        return 0.0
    
    return sum(response_times) / len(response_times)


def _get_connection_trend() -> list:
    """Obtém tendência de conexões nas últimas horas"""
    # Implementação simplificada - pode ser expandida para análise temporal mais sofisticada
    return [websocket_handler.get_connection_count()]


def _get_message_trend() -> list:
    """Obtém tendência de mensagens nas últimas horas"""
    # Implementação simplificada
    return [_calculate_messages_per_minute()]


def _get_error_trend() -> list:
    """Obtém tendência de erros nas últimas horas"""
    # Implementação simplificada
    return [_calculate_error_rate()]


@app.post("/admin/circuit-breaker/reset")
async def reset_circuit_breaker():
    """
    Endpoint administrativo para resetar o circuit breaker manualmente.
    Útil para recuperação manual após incidentes.
    """
    try:
        error_recovery = websocket_handler.get_error_recovery()
        error_recovery.reset_circuit_breaker()
        
        websocket_logger.system_event("circuit_breaker_manual_reset", "Circuit breaker resetado manualmente via API")
        
        return {
            "message": "Circuit breaker resetado com sucesso",
            "timestamp": websocket_handler._get_current_timestamp(),
            "new_state": error_recovery.circuit_state.value
        }
    except Exception as e:
        logger.error(f"Erro ao resetar circuit breaker: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@app.get("/admin/errors/recent")
async def get_recent_errors(minutes: int = Query(5, ge=1, le=60, description="Minutos para buscar erros")):
    """
    Endpoint para visualizar erros recentes para diagnóstico.
    
    Args:
        minutes: Número de minutos para buscar erros (padrão: 5)
    """
    try:
        error_recovery = websocket_handler.get_error_recovery()
        recent_errors = error_recovery._get_recent_errors(minutes)
        
        return {
            "time_window_minutes": minutes,
            "total_errors": len(recent_errors),
            "errors": [
                {
                    "timestamp": error.timestamp.isoformat(),
                    "error_type": error.error_type,
                    "error_code": error.error_code,
                    "severity": error.severity.value,
                    "connection_id": error.connection_id,
                    "recoverable": error.recoverable,
                    "recovery_attempted": error.recovery_attempted
                }
                for error in recent_errors
            ]
        }
    except Exception as e:
        logger.error(f"Erro ao buscar erros recentes: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@app.post("/admin/monitoring/reset")
async def reset_monitoring_metrics():
    """
    Endpoint administrativo para resetar todas as métricas de monitoramento.
    Útil para testes ou limpeza de dados históricos.
    """
    try:
        performance_monitor.reset_metrics()
        websocket_logger.system_event("monitoring_metrics_reset", "Métricas de monitoramento resetadas manualmente")
        
        return {
            "message": "Métricas de monitoramento resetadas com sucesso",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        logger.error(f"Erro ao resetar métricas: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@app.get("/ws/connections")
async def get_websocket_connections():
    """
    Endpoint para visualizar informações detalhadas das conexões WebSocket ativas.
    Útil para monitoramento e debug.
    """
    connection_manager = websocket_handler.get_connection_manager()
    
    return {
        "total_connections": connection_manager.get_connection_count(),
        "connections": connection_manager.get_all_connections_info(),
        "timestamp": websocket_handler._get_current_timestamp()
    }


@app.get("/ws/protocol")
async def get_websocket_protocol():
    """
    Endpoint para documentar o protocolo de mensagens WebSocket suportado.
    Retorna informações sobre tipos de mensagem, formatos e exemplos.
    """
    protocol = websocket_handler.get_message_protocol()
    
    return {
        "protocol_version": "1.0",
        "description": "Protocolo estruturado de mensagens WebSocket para comunicação com o frontend",
        "supported_message_types": protocol.get_supported_message_types(),
        "message_examples": {
            "text_message": {
                "type": "text",
                "text": "Olá, servidor!",
                "metadata": {"source": "user_input"}
            },
            "audio_data_message": {
                "type": "audio_data",
                "audio_data": "UklGRn...",  # base64 encoded audio
                "format": "pcm_16_16000",
                "duration_ms": 1000,
                "sample_rate": 16000,
                "channels": 1
            },
            "broadcast_request": {
                "type": "broadcast_request",
                "message": "Mensagem para todos",
                "exclude_sender": True,
                "target_connections": None  # ou lista de IDs específicos
            },
            "connection_info_request": {
                "type": "connection_info_request"
            },
            "ping": {
                "type": "ping",
                "data": "test"
            }
        },
        "response_examples": {
            "response": {
                "type": "response",
                "message": "Echo: Olá, servidor!",
                "connection_id": "uuid-da-conexao",
                "original_message": "Olá, servidor!",
                "processing_time_ms": 5,
                "timestamp": "2025-06-08T01:30:00Z"
            },
            "audio_received": {
                "type": "audio_received",
                "size_bytes": 1024,
                "format": "pcm_16_16000",
                "message": "Áudio recebido: 1024 bytes",
                "connection_id": "uuid-da-conexao",
                "processing_time_ms": 10,
                "timestamp": "2025-06-08T01:30:00Z"
            },
            "error": {
                "type": "error",
                "error_code": "INVALID_MESSAGE",
                "message": "Formato de mensagem inválido",
                "connection_id": "uuid-da-conexao",
                "details": None,
                "timestamp": "2025-06-08T01:30:00Z"
            }
        },
        "error_handling": {
            "circuit_breaker": "Sistema de proteção contra falhas em cascata",
            "retry_logic": "Tentativas automáticas com backoff exponencial",
            "error_classification": "Categorização por severidade e tipo",
            "recovery_strategies": "Estratégias específicas por tipo de erro"
        },
        "audio_formats": {
            "pcm_16_16000": "PCM 16-bit, 16kHz (padrão para Gemini)",
            "webm_opus": "WebM com codec Opus",
            "mp3": "MP3 padrão",
            "wav": "WAV padrão"
        },
        "notes": [
            "Todas as mensagens devem ter o campo 'type' obrigatório",
            "Dados de áudio devem ser codificados em base64",
            "Timestamps são gerados automaticamente no formato ISO 8601",
            "IDs de conexão são atribuídos automaticamente pelo servidor",
            "Mensagens de erro incluem códigos estruturados para tratamento programático",
            "Sistema implementa circuit breaker para proteção contra falhas",
            "Retry automático com backoff exponencial para erros recuperáveis"
        ]
    }


@app.websocket("/ws/voice")
async def websocket_voice_endpoint(websocket: WebSocket):
    """
    Endpoint WebSocket principal para comunicação de voz com o frontend.
    Utiliza WebSocketHandler para gerenciar a lógica de comunicação.
    Suporta múltiplas conexões simultâneas através do ConnectionManager.
    Implementa protocolo estruturado de mensagens com validação.
    Inclui sistema robusto de tratamento de erros e recuperação.
    """
    await websocket_handler.handle_connection(websocket)


if __name__ == "__main__":
    # Executar servidor de desenvolvimento
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    ) 