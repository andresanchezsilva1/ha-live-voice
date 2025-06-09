# backend/poc_app/main.py
import os
from pathlib import Path
from dotenv import load_dotenv

# Carregar variáveis de ambiente do arquivo .env
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ Arquivo .env carregado: {env_path}")
else:
    print(f"⚠️  Arquivo .env não encontrado: {env_path}")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from poc_app.core.config import settings
from poc_app.core.websocket_handler import WebSocketHandler
from poc_app.core.message_protocol import MessageProtocol
from poc_app.core.error_recovery import HealthStatus
from poc_app.core.performance_monitor import performance_monitor, MetricType
from poc_app.core.structured_logger import websocket_logger, setup_logging
from poc_app.core.app import GeminiHomeAssistantApp
from poc_app.core.exceptions import SessionNotFoundError, AudioProcessingError, IntegrationError
from poc_app.core.config_validator import validate_app_config, ConfigValidator
from poc_app.models.config import ApplicationConfig
import logging
import uvicorn
import asyncio
import json
from uuid import uuid4
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

# Instância de configuração validada
app_config: Optional[ApplicationConfig] = None

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
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://localhost:5174", "http://localhost:5175", "http://localhost:8080"],  # URLs típicas do Vue dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instanciar o gerenciador WebSocket (endpoint legado)
websocket_handler = WebSocketHandler()

# Instanciar a aplicação principal de integração
gemini_ha_app: Optional[GeminiHomeAssistantApp] = None

@app.on_event("startup")
async def startup_event():
    """Eventos de inicialização da aplicação"""
    global gemini_ha_app, app_config
    
    websocket_logger.system_event("app_startup", "Aplicação FastAPI iniciada")
    logger.info("Aplicação Home Assistant Voice Control POC iniciada")
    
    # Validar configuração na inicialização
    try:
        logger.info("🔧 Validando configuração da aplicação...")
        app_config = await validate_app_config(skip_connectivity=True)  # Skip connectivity para evitar delay no startup
        logger.info("✅ Configuração validada com sucesso")
    except SystemExit:
        logger.error("❌ Configuração inválida - aplicação será encerrada")
        return
    except Exception as e:
        logger.error(f"❌ Erro inesperado na validação: {e}")
        return
    
    # Inicializar a aplicação principal usando configuração validada
    try:
        gemini_ha_app = GeminiHomeAssistantApp(
            gemini_api_key=app_config.gemini.api_key,
            ha_url=app_config.home_assistant.url,
            ha_token=app_config.home_assistant.access_token,
            session_timeout_minutes=app_config.session.max_session_age_minutes,
            cleanup_interval_seconds=app_config.session.cleanup_interval_seconds
        )
        await gemini_ha_app.start()
        logger.info("GeminiHomeAssistantApp inicializada com sucesso")
    except Exception as e:
        logger.error(f"Erro ao inicializar GeminiHomeAssistantApp: {e}")
        gemini_ha_app = None

@app.on_event("shutdown")
async def shutdown_event():
    """Eventos de encerramento da aplicação"""
    global gemini_ha_app
    
    if gemini_ha_app:
        try:
            await gemini_ha_app.stop()
            logger.info("GeminiHomeAssistantApp finalizada com sucesso")
        except Exception as e:
            logger.error(f"Erro ao finalizar GeminiHomeAssistantApp: {e}")
    
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
    
    # Verificar status da aplicação integrada
    integration_status = "available" if gemini_ha_app else "unavailable"
    integration_stats = None
    if gemini_ha_app:
        try:
            integration_stats = gemini_ha_app.get_session_stats()
        except Exception as e:
            logger.warning(f"Erro ao obter stats da integração: {e}")
            integration_status = "error"
    
    return {
        "status": health_status.value,
        "system_health": {
            "overall": health_status.value,
            "circuit_breaker": error_recovery.circuit_state.value,
            "active_connections": websocket_handler.get_connection_count(),
            "integration_status": integration_status
        },
        "services": {
            "gemini_api_configured": bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "sua_chave_gemini_aqui"),
            "ha_configured": bool(settings.HA_URL and settings.HA_LLAT and settings.HA_LLAT != "seu_token_home_assistant_aqui"),
        },
        "audio_config": {
            "sample_rate": settings.AUDIO_SAMPLE_RATE_GEMINI,
            "channels": settings.AUDIO_CHANNELS_GEMINI
        },
        "websocket_connections": websocket_handler.get_connection_count(),
        "integration": {
            "status": integration_status,
            "stats": integration_stats
        }
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


@app.get("/integration/stats")
async def get_integration_stats():
    """
    Endpoint para obter estatísticas da aplicação integrada.
    Retorna informações sobre sessões ativas, métricas de processamento e status.
    """
    if not gemini_ha_app:
        return {
            "status": "unavailable",
            "message": "GeminiHomeAssistantApp não está inicializada",
            "stats": None
        }
    
    try:
        stats = gemini_ha_app.get_session_stats()
        return {
            "status": "active",
            "timestamp": datetime.now().isoformat(),
            "stats": stats,
            "configuration": {
                "session_timeout_minutes": gemini_ha_app.session_timeout_minutes,
                "cleanup_interval_seconds": gemini_ha_app.cleanup_interval_seconds
            }
        }
    except Exception as e:
        logger.error(f"Erro ao obter estatísticas: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Endpoint WebSocket principal integrado com Gemini e Home Assistant.
    
    Este endpoint oferece uma interface simplificada que integra automaticamente:
    - Captura e processamento de áudio via Gemini Live API
    - Execução de comandos do Home Assistant
    - Retorno de respostas em áudio
    
    Protocolo de mensagens:
    - Envio inicial: JSON com tipo 'status' para inicialização
    - Envio de áudio: dados de áudio em formato binário (streaming)
    - Recebimento: JSON com transcription/function_result e áudio binário como resposta
    """
    if not gemini_ha_app:
        logger.error("GeminiHomeAssistantApp não está disponível")
        await websocket.close(code=1011, reason="Serviço não disponível")
        return
    
    await websocket.accept()
    session_id = None
    client_initialized = False
    
    try:
        # Criar sessão única para esta conexão
        session_id = await gemini_ha_app.create_session()
        logger.info(f"Nova conexão WebSocket estabelecida com sessão {session_id}")
        
        # Enviar confirmação de conexão
        await websocket.send_json({
            "type": "connection_established",
            "session_id": session_id,
            "timestamp": datetime.now().isoformat()
        })
        
        # Buffer para acumular chunks de áudio
        audio_buffer = bytearray()
        last_processing_time = datetime.now()
        processing_interval = 2.0  # Processar a cada 2 segundos de áudio
        
        while True:
            try:
                # Receber dados (pode ser JSON ou binário)
                raw_data = await websocket.receive()
                
                # DEBUG: Log completo do que está sendo recebido
                logger.info(f"🔍 [DEBUG-RECEIVE] Dados recebidos: type={raw_data.get('type', 'NO_TYPE')}")
                logger.info(f"🔍 [DEBUG-RECEIVE] Keys disponíveis: {list(raw_data.keys())}")
                if "text" in raw_data:
                    logger.info(f"🔍 [DEBUG-RECEIVE] Text content: {raw_data['text'][:200]}...")
                if "bytes" in raw_data:
                    logger.info(f"🔍 [DEBUG-RECEIVE] Bytes length: {len(raw_data['bytes'])}")
                
                # Verificar se cliente foi inicializado
                if raw_data.get("type") == "websocket.receive":
                    if "text" in raw_data and not client_initialized:
                        # Primeira mensagem deve ser inicialização
                        try:
                            message = json.loads(raw_data["text"])
                            logger.info(f"🔍 [DEBUG-JSON] Message parsed: {message}")
                            if message.get("type") == "init":
                                client_initialized = True
                                logger.info(f"Cliente inicializado para sessão {session_id}")
                                
                                # Gerar e enviar áudio de boas-vindas usando função com WebSocket streaming
                                try:
                                    welcome_result = await gemini_ha_app.send_welcome_message_with_websocket(session_id, websocket)
                                    
                                    # Enviar resposta de texto atualizada se disponível
                                    if welcome_result.get("response_text"):
                                        await websocket.send_json({
                                            "type": "response",
                                            "content": welcome_result["response_text"],
                                            "timestamp": datetime.now().isoformat()
                                        })
                                    
                                except Exception as e:
                                    logger.warning(f"Não foi possível gerar áudio de boas-vindas: {e}")
                                    # Não é um erro crítico, continuar sem áudio
                                
                                continue
                            elif message.get("type") == "start_recording":
                                # Iniciar gravação manual
                                logger.info(f"🎙️ [MANUAL-START] Iniciando gravação para sessão {session_id}")
                                try:
                                    # 🔥 GARANTIR SESSÃO PERSISTENTE ESTÁ ATIVA
                                    await gemini_ha_app._ensure_global_session()
                                    
                                    if not gemini_ha_app._session_healthy:
                                        logger.error(f"❌ [START-RECORDING] Sessão persistente não está saudável")
                                        raise Exception("Sessão persistente não está saudável")
                                    
                                    await gemini_ha_app.gemini_client.start_recording()
                                    await websocket.send_json({
                                        "type": "recording_started",
                                        "message": "Gravação iniciada",
                                        "timestamp": datetime.now().isoformat()
                                    })
                                except Exception as e:
                                    logger.error(f"Erro ao iniciar gravação: {e}")
                                    await websocket.send_json({
                                        "type": "error",
                                        "message": f"Erro ao iniciar gravação: {e}",
                                        "timestamp": datetime.now().isoformat()
                                    })
                                continue
                            elif message.get("type") == "stop_recording":
                                # Método simplificado baseado no script oficial Google
                                logger.info(f"🛑 [SIMPLE-STOP] Stop recording - método simplificado")
                                try:
                                    # Para de aceitar novos áudios
                                    await gemini_ha_app.gemini_client.stop_recording()
                                    
                                    # Confirma que parou
                                    await websocket.send_json({
                                        "type": "recording_stopped",
                                        "message": "Gravação finalizada",
                                        "timestamp": datetime.now().isoformat()
                                    })
                                    
                                    # Inicia coleta de resposta em background (como Google faz)
                                    asyncio.create_task(gemini_ha_app.simple_collect_response(session_id, websocket))
                                    
                                except Exception as e:
                                    logger.error(f"❌ [SIMPLE-STOP] Erro: {e}")
                                    await websocket.send_json({
                                        "type": "error",
                                        "message": f"Erro ao processar: {str(e)}",
                                        "timestamp": datetime.now().isoformat()
                                    })
                                continue
                            elif message.get("type") == "status" and message.get("content") == "client_disconnecting":
                                logger.info(f"Cliente desconectando sessão {session_id}")
                                break
                        except json.JSONDecodeError:
                            logger.warning("Mensagem JSON inválida recebida durante inicialização")
                            continue
                    elif "text" in raw_data and client_initialized:
                        # Processar mensagens de controle mesmo após inicialização
                        try:
                            message = json.loads(raw_data["text"])
                            logger.info(f"🔍 [DEBUG-JSON-INIT] Message after init: {message}")
                            
                            if message.get("type") == "start_recording":
                                # Iniciar gravação manual
                                logger.info(f"🎙️ [MANUAL-START] Iniciando gravação para sessão {session_id}")
                                try:
                                    # 🔥 GARANTIR SESSÃO PERSISTENTE ESTÁ ATIVA
                                    await gemini_ha_app._ensure_global_session()
                                    
                                    if not gemini_ha_app._session_healthy:
                                        logger.error(f"❌ [START-RECORDING] Sessão persistente não está saudável")
                                        raise Exception("Sessão persistente não está saudável")
                                    
                                    await gemini_ha_app.gemini_client.start_recording()
                                    await websocket.send_json({
                                        "type": "recording_started",
                                        "message": "Gravação iniciada",
                                        "timestamp": datetime.now().isoformat()
                                    })
                                except Exception as e:
                                    logger.error(f"Erro ao iniciar gravação: {e}")
                                    await websocket.send_json({
                                        "type": "error",
                                        "message": f"Erro ao iniciar gravação: {e}",
                                        "timestamp": datetime.now().isoformat()
                                    })
                                continue
                            elif message.get("type") == "stop_recording":
                                # Método simplificado baseado no script oficial Google
                                logger.info(f"🛑 [SIMPLE-STOP] Stop recording - método simplificado (pós-init)")
                                try:
                                    # Para de aceitar novos áudios
                                    await gemini_ha_app.gemini_client.stop_recording()
                                    
                                    # Confirma que parou
                                    await websocket.send_json({
                                        "type": "recording_stopped",
                                        "message": "Gravação finalizada",
                                        "timestamp": datetime.now().isoformat()
                                    })
                                    
                                    # Inicia coleta de resposta em background (como Google faz)
                                    asyncio.create_task(gemini_ha_app.simple_collect_response(session_id, websocket))
                                    
                                except Exception as e:
                                    logger.error(f"❌ [SIMPLE-STOP] Erro: {e}")
                                    await websocket.send_json({
                                        "type": "error",
                                        "message": f"Erro ao processar: {str(e)}",
                                        "timestamp": datetime.now().isoformat()
                                    })
                                continue
                            elif message.get("type") == "status" and message.get("content") == "client_disconnecting":
                                logger.info(f"Cliente desconectando sessão {session_id}")
                                break
                        except json.JSONDecodeError as e:
                            logger.warning(f"Mensagem JSON inválida recebida após inicialização: {e}")
                            continue
                    elif "bytes" in raw_data and client_initialized:
                        # Dados de áudio - processar imediatamente em tempo real
                        audio_chunk = raw_data["bytes"]
                        logger.debug(f"🎤 [AUDIO-IN] Recebendo chunk de áudio: {len(audio_chunk)} bytes")
                        
                        try:
                            # 🔥 VERIFICAR SESSÃO PERSISTENTE ANTES DE ENVIAR
                            if not gemini_ha_app._session_healthy:
                                logger.warning(f"⚠️ [DISCONNECTED] Sessão persistente não saudável, ignorando chunk de áudio")
                                continue
                            
                            # Enviar chunk imediatamente para o Gemini (streaming em tempo real)
                            logger.debug(f"🔄 [REAL-TIME] Enviando chunk de {len(audio_chunk)} bytes para Gemini (sessão persistente)")
                            
                            # Enviar chunk diretamente para o Gemini
                            await gemini_ha_app.gemini_client.send_audio_data(audio_chunk)
                            logger.debug(f"✅ [REAL-TIME] Chunk enviado com sucesso para Gemini")
                            
                        except Exception as e:
                            if "keepalive ping timeout" in str(e):
                                logger.warning(f"⚠️ [KEEPALIVE-TIMEOUT] Conexão com Gemini perdida (sessão {session_id}). Ignorando chunks futuros até reconnect.")
                                # Não quebrar o loop, apenas parar de enviar chunks
                                continue
                            else:
                                logger.warning(f"❌ [AUDIO-ERROR] Erro ao enviar chunk para Gemini: {e}")
                        
                        # Enviar confirmação de recebimento periodicamente
                        if len(audio_chunk) > 0:  # Confirmar cada chunk recebido
                            try:
                                await websocket.send_json({
                                    "type": "audio_received",
                                    "chunk_size": len(audio_chunk),
                                    "timestamp": datetime.now().isoformat()
                                })
                            except Exception as send_error:
                                logger.debug(f"Erro ao enviar confirmação: {send_error}")
                                
                    elif "bytes" in raw_data and not client_initialized:
                        # Dados de áudio recebidos antes da inicialização - ignorar
                        logger.warning("Dados de áudio recebidos antes da inicialização do cliente")
                        continue
                elif raw_data.get("type") == "websocket.disconnect":
                    logger.info(f"Cliente desconectado (sessão: {session_id})")
                    break
                else:
                    continue  # Ignorar outros tipos de mensagem
                    
            except Exception as e:
                logger.error(f"Erro ao processar dados: {e}")
                break
                
    except WebSocketDisconnect:
        logger.info(f"Cliente desconectado (sessão: {session_id})")
        
    except Exception as e:
        logger.error(f"Erro na conexão WebSocket: {e}")
        
    finally:
        # Limpar sessão ao finalizar conexão
        if session_id and gemini_ha_app:
            await gemini_ha_app.close_session(session_id)
            logger.info(f"Sessão {session_id} finalizada")


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


@app.get("/config/status")
async def get_config_status():
    """Endpoint para verificar status da configuração."""
    global app_config
    
    if not app_config:
        return {
            "status": "not_validated",
            "message": "Configuração não foi validada durante a inicialização",
            "valid": False
        }
    
    # Executar validação completa (incluindo conectividade)
    try:
        validator = ConfigValidator(app_config)
        results = await validator.validate_all(skip_connectivity=False)
        
        return {
            "status": "validated",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "validation_results": results,
            "config_summary": {
                "app_name": app_config.app_name,
                "version": app_config.version,
                "debug": app_config.debug,
                "gemini_model": app_config.gemini.model_name,
                "ha_url": app_config.home_assistant.url,
                "websocket_port": app_config.websocket.port,
                "log_level": app_config.logging.level.value
            }
        }
    except Exception as e:
        logger.error(f"Erro na validação de configuração: {e}")
        return {
            "status": "error",
            "message": f"Erro durante validação: {str(e)}",
            "valid": False
        }


@app.get("/config/details")
async def get_config_details():
    """Endpoint para obter detalhes da configuração (dados não-sensíveis)."""
    global app_config
    
    if not app_config:
        return {
            "error": "Configuração não disponível",
            "message": "Aplicação não foi inicializada corretamente"
        }
    
    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "configuration": app_config.to_dict(),
        "validation_info": {
            "config_source": "environment_variables",
            "validation_time": "startup",
            "last_validated": datetime.utcnow().isoformat() + "Z"
        }
    }


@app.post("/config/validate")
async def validate_config_manual():
    """Endpoint para validação manual da configuração."""
    global app_config
    
    if not app_config:
        return {
            "status": "error",
            "message": "Configuração não foi inicializada",
            "valid": False
        }
    
    try:
        validator = ConfigValidator(app_config)
        results = await validator.validate_all(skip_connectivity=False)
        
        return {
            "status": "validated",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "validation_results": results,
            "valid": results["config_structure"]["valid"] and 
                    results["environment_variables"]["valid"] and 
                    results["connectivity"]["valid"]
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Erro durante validação: {str(e)}",
            "valid": False
        }


# ============================================================
# ENDPOINTS DE GERENCIAMENTO DE SESSÕES
# ============================================================

@app.get("/sessions/stats")
async def get_session_statistics():
    """Endpoint para obter estatísticas detalhadas das sessões ativas."""
    try:
        stats = gemini_ha_app.get_session_stats()
        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "statistics": stats
        }
    except Exception as e:
        logger.error(f"Error getting session stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get session statistics: {str(e)}")

@app.get("/sessions/health")
async def get_session_health_report():
    """Endpoint para obter relatório de saúde das sessões."""
    try:
        health_report = gemini_ha_app.get_session_health_report()
        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "health_report": health_report
        }
    except Exception as e:
        logger.error(f"Error getting session health report: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get health report: {str(e)}")

@app.get("/sessions/{session_id}")
async def get_session_details(session_id: str):
    """Endpoint para obter detalhes de uma sessão específica."""
    try:
        session_details = gemini_ha_app.get_session_by_id(session_id)
        if session_details is None:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        
        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "session": session_details
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session details: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get session details: {str(e)}")

@app.post("/sessions/cleanup")
async def manual_session_cleanup(
    max_age_minutes: Optional[int] = Query(None, description="Idade máxima das sessões em minutos"),
    max_idle_minutes: Optional[int] = Query(None, description="Tempo máximo de inatividade em minutos"),
    force_unhealthy: bool = Query(False, description="Forçar limpeza de sessões não saudáveis")
):
    """Endpoint para limpeza manual de sessões."""
    try:
        cleanup_results = await gemini_ha_app.cleanup_old_sessions(max_age_minutes, max_idle_minutes)
        
        if force_unhealthy:
            unhealthy_cleanup = await gemini_ha_app.force_cleanup_unhealthy_sessions()
            cleanup_results["unhealthy_cleanup"] = unhealthy_cleanup
        
        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "cleanup_results": cleanup_results
        }
    except Exception as e:
        logger.error(f"Error during manual cleanup: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cleanup sessions: {str(e)}")

@app.post("/sessions/optimize")
async def optimize_sessions():
    """Endpoint para otimização completa das sessões."""
    try:
        optimization_results = await gemini_ha_app.optimize_sessions()
        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "optimization_results": optimization_results
        }
    except Exception as e:
        logger.error(f"Error during session optimization: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to optimize sessions: {str(e)}")

@app.delete("/sessions/{session_id}")
async def close_session_endpoint(session_id: str):
    """Endpoint para fechar uma sessão específica."""
    try:
        success = await gemini_ha_app.close_session(session_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        
        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "message": f"Session {session_id} closed successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error closing session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to close session: {str(e)}")

@app.post("/sessions/cleanup/unhealthy")
async def force_cleanup_unhealthy():
    """Endpoint para limpeza forçada de sessões não saudáveis."""
    try:
        cleanup_results = await gemini_ha_app.force_cleanup_unhealthy_sessions()
        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "cleanup_results": cleanup_results
        }
    except Exception as e:
        logger.error(f"Error during unhealthy session cleanup: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cleanup unhealthy sessions: {str(e)}")


if __name__ == "__main__":
    # Executar servidor de desenvolvimento
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    ) 