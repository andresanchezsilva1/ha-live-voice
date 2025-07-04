from fastapi import WebSocket, WebSocketDisconnect
import logging
from typing import Dict, Any, Optional
import time
import json
from .connection_manager import ConnectionManager
from .message_protocol import (
    MessageProtocol, BaseMessage, MessageType,
    TextMessage, AudioDataMessage, BroadcastRequestMessage,
    ConnectionInfoRequestMessage, PingMessage,
    ResponseMessage, AudioReceivedMessage, BroadcastMessage,
    BroadcastConfirmationMessage, ConnectionInfoMessage, ErrorMessage, PongMessage
)
from .exceptions import (
    WebSocketError, MessageParsingError, AudioProcessingError, 
    BroadcastError, ProtocolViolationError, ConnectionError
)
from .error_recovery import ErrorRecoveryManager, RetryConfig, CircuitBreakerConfig
from .performance_monitor import performance_monitor, MetricType
from .structured_logger import websocket_logger, log_async_operation

logger = logging.getLogger(__name__)


class WebSocketHandler:
    """
    Classe responsável por gerenciar a lógica do endpoint WebSocket.
    Encapsula o comportamento de comunicação com o frontend Vue3.
    Utiliza ConnectionManager para gerenciar múltiplas conexões simultâneas.
    Utiliza MessageProtocol para estruturar e validar mensagens.
    Implementa sistema robusto de recuperação de erros.
    Inclui monitoramento avançado de performance e logging estruturado.
    """
    
    def __init__(self):
        self.connection_manager = ConnectionManager()
        self.protocol = MessageProtocol()
        
        # Configurar sistema de recuperação de erros
        retry_config = RetryConfig(
            max_attempts=3,
            initial_delay=0.5,
            max_delay=10.0,
            backoff_factor=2.0,
            jitter=True
        )
        
        circuit_config = CircuitBreakerConfig(
            failure_threshold=5,
            recovery_timeout=30.0,
            half_open_max_calls=3
        )
        
        self.error_recovery = ErrorRecoveryManager(retry_config, circuit_config)
        
        # Configurar callbacks para notificações de erro
        self.error_recovery.set_callbacks(
            on_circuit_opened=self._on_circuit_opened,
            on_circuit_closed=self._on_circuit_closed,
            on_critical_error=self._on_critical_error
        )
        
        # Iniciar monitoramento de performance
        performance_monitor.start_monitoring()
        
        # Log de inicialização
        websocket_logger.system_event("handler_initialized", "WebSocketHandler inicializado com sucesso")
    
    @log_async_operation("websocket_connection")
    async def handle_connection(self, websocket: WebSocket) -> None:
        """
        Gerencia uma conexão WebSocket individual com tratamento robusto de erros.
        
        Args:
            websocket: Instância do WebSocket a ser gerenciada
        """
        connection_id = None
        start_time = time.time()
        
        try:
            # Conectar usando o ConnectionManager com recuperação
            connection_id = await self.error_recovery.execute_with_recovery(
                operation=lambda: self.connection_manager.connect(websocket),
                error_context={"operation": "websocket_connection"}
            )
            
            # Garantir que o monitoramento está ativo
            await performance_monitor.ensure_monitoring_started()
            
            # Registrar métricas e logs
            performance_monitor.record_connection_start(connection_id)
            
            # Obter informações da conexão para logging
            remote_addr = getattr(websocket.client, 'host', None) if hasattr(websocket, 'client') else None
            user_agent = None
            if hasattr(websocket, 'headers'):
                user_agent = websocket.headers.get('user-agent')
            
            websocket_logger.connection_started(
                connection_id=connection_id,
                remote_addr=remote_addr,
                user_agent=user_agent
            )
            
            # Loop principal de processamento de mensagens
            while True:
                try:
                    # Receber dados do frontend Vue3
                    raw_data = await websocket.receive()
                    
                    # Processar dados baseado no tipo
                    if raw_data.get("type") == "websocket.receive":
                        if "text" in raw_data:
                            # Mensagem de texto (JSON)
                            message_text = raw_data["text"]
                            await self.error_recovery.execute_with_recovery(
                                operation=lambda: self._process_raw_message(websocket, connection_id, message_text),
                                connection_id=connection_id,
                                error_context={"operation": "text_message_processing", "data_type": "text"}
                            )
                        elif "bytes" in raw_data:
                            # Dados binários (áudio PCM)
                            audio_bytes = raw_data["bytes"]
                            # Para dados de áudio, não usar recovery se a conexão for fechada
                            try:
                                await self._process_audio_data(websocket, connection_id, audio_bytes)
                            except Exception as audio_error:
                                # Se erro durante processamento de áudio, verificar se é desconexão
                                if "disconnect" in str(audio_error).lower() or "closed" in str(audio_error).lower():
                                    logger.debug(f"Conexão {connection_id} fechada durante processamento de áudio")
                                    break
                                else:
                                    # Outros erros de áudio podem usar recovery
                                    raise audio_error
                        else:
                            continue  # Ignorar mensagens sem conteúdo
                    elif raw_data.get("type") == "websocket.disconnect":
                        # Desconexão explícita detectada
                        logger.info(f"Desconexão explícita detectada para {connection_id}")
                        self._handle_connection_cleanup(connection_id, start_time, "explicit_disconnect")
                        break
                    else:
                        continue  # Ignorar outros tipos de mensagem
                    
                except WebSocketDisconnect:
                    # Desconexão normal - não é um erro
                    logger.info(f"WebSocketDisconnect detectado para {connection_id}")
                    self._handle_connection_cleanup(connection_id, start_time, "normal_disconnect")
                    websocket_logger.connection_ended(
                        connection_id=connection_id,
                        duration_seconds=time.time() - start_time,
                        reason="normal_disconnect"
                    )
                    break
                    
                except Exception as e:
                    error_message = str(e).lower()
                    
                    # Verificar se é erro relacionado à desconexão (não deve usar recovery)
                    if any(keyword in error_message for keyword in [
                        "disconnect", "closed", "cannot call \"receive\"", 
                        "websocket.close", "connection closed"
                    ]):
                        logger.info(f"Erro de desconexão detectado para {connection_id}: {e}")
                        self._handle_connection_cleanup(connection_id, start_time, "disconnect_error")
                        websocket_logger.connection_ended(
                            connection_id=connection_id,
                            duration_seconds=time.time() - start_time,
                            reason="disconnect_error"
                        )
                        break
                    else:
                        # Outros erros podem usar recovery
                        logger.warning(f"Erro não relacionado à desconexão para {connection_id}: {e}")
                        await self._handle_connection_error(websocket, connection_id, e)
                        self._handle_connection_cleanup(connection_id, start_time, f"error: {type(e).__name__}")
                        break
                    
        except Exception as e:
            # Erro na conexão inicial
            logger.error(f"Erro crítico na conexão WebSocket: {e}", exc_info=True)
            websocket_logger.error_occurred(
                connection_id=connection_id,
                error_type=type(e).__name__,
                error_code="CONNECTION_INIT_ERROR",
                error_message=str(e),
                severity="critical"
            )
            
            if connection_id:
                self._handle_connection_cleanup(connection_id, start_time, f"init_error: {type(e).__name__}")
            
            try:
                await websocket.close()
            except:
                pass
    
    def _handle_connection_cleanup(self, connection_id: str, start_time: float, reason: str) -> None:
        """Cleanup de conexão com métricas e logging"""
        if connection_id:
            self.connection_manager.disconnect_by_id(connection_id)
            
            # Registrar métricas
            performance_monitor.record_connection_end(connection_id)
            
            # Calcular duração
            duration = time.time() - start_time
            performance_monitor.record_metric(
                MetricType.CONNECTION,
                "connection.session_duration",
                duration,
                tags={"connection_id": connection_id, "reason": reason}
            )
    
    async def _handle_connection_error(self, websocket: WebSocket, connection_id: str, error: Exception) -> None:
        """
        Trata erros de conexão de forma robusta.
        
        Args:
            websocket: Instância do WebSocket
            connection_id: ID da conexão
            error: Erro ocorrido
        """
        try:
            # Converter para WebSocketError se necessário
            if isinstance(error, WebSocketError):
                websocket_error = error
            else:
                websocket_error = ConnectionError(
                    message=f"Erro de conexão: {str(error)}",
                    connection_id=connection_id,
                    details={"original_error": str(error), "error_type": type(error).__name__}
                )
            
            # Log do erro
            websocket_logger.error_occurred(
                connection_id=connection_id,
                error_type=type(websocket_error).__name__,
                error_code=websocket_error.error_code,
                error_message=websocket_error.message,
                severity=websocket_error.severity.value
            )
            
            # Registrar métrica de erro
            performance_monitor.record_error(
                connection_id=connection_id,
                error_type=type(websocket_error).__name__,
                error_code=websocket_error.error_code,
                severity=websocket_error.severity.value
            )
            
            # Tentar enviar erro para o cliente antes de desconectar
            if websocket_error.recoverable:
                await self._send_error_message(connection_id, websocket_error.error_code, websocket_error.message)
            
            # Fechar WebSocket se ainda estiver aberto
            try:
                await websocket.close()
            except:
                pass
                
        except Exception as cleanup_error:
            logger.error(f"Erro durante cleanup da conexão {connection_id}: {cleanup_error}")
            websocket_logger.error(
                f"Erro durante cleanup da conexão {connection_id}: {cleanup_error}",
                connection_id=connection_id,
                cleanup_error=str(cleanup_error)
            )
    
    @log_async_operation("message_processing")
    async def _process_raw_message(self, websocket: WebSocket, connection_id: str, raw_data: str) -> None:
        """
        Processa dados brutos recebidos do cliente usando o protocolo estruturado.
        
        Args:
            websocket: Instância do WebSocket
            connection_id: ID único da conexão
            raw_data: Dados brutos recebidos do WebSocket (string JSON)
        """
        start_time = time.time()
        message_size = len(raw_data.encode('utf-8'))
        
        try:
            # Parsear mensagem usando o protocolo
            message = self.protocol.parse_message(raw_data)
            
            if not message:
                raise MessageParsingError(
                    "Formato de mensagem inválido ou não suportado",
                    raw_data=raw_data,
                    connection_id=connection_id
                )
            
            # Log de mensagem recebida
            websocket_logger.message_received(
                connection_id=connection_id,
                message_type=str(message.type),
                size_bytes=message_size
            )
            
            # Registrar métrica de mensagem recebida
            performance_monitor.record_message_received(
                connection_id=connection_id,
                message_type=str(message.type),
                size_bytes=message_size
            )
            
            # Definir connection_id na mensagem se não estiver presente
            if not message.connection_id:
                message.connection_id = connection_id
            
            # Roteamento baseado no tipo da mensagem
            if isinstance(message, TextMessage):
                await self._handle_text_message(connection_id, message, start_time)
            elif isinstance(message, AudioDataMessage):
                await self._handle_audio_message(connection_id, message, start_time)
            elif isinstance(message, BroadcastRequestMessage):
                await self._handle_broadcast_request(connection_id, message)
            elif isinstance(message, ConnectionInfoRequestMessage):
                await self._handle_connection_info_request(connection_id, message)
            elif isinstance(message, PingMessage):
                await self._handle_ping_message(connection_id, message)
            else:
                raise ProtocolViolationError(
                    f"Tipo de mensagem não implementado: {message.type}",
                    received_type=str(message.type),
                    connection_id=connection_id
                )
                
        except WebSocketError as e:
            # Log e métricas de erro
            websocket_logger.error_occurred(
                connection_id=connection_id,
                error_type=type(e).__name__,
                error_code=e.error_code,
                error_message=e.message,
                severity=e.severity.value
            )
            
            performance_monitor.record_error(
                connection_id=connection_id,
                error_type=type(e).__name__,
                error_code=e.error_code,
                severity=e.severity.value
            )
            
            # Re-raise WebSocketError para manter informações específicas
            raise
        except Exception as e:
            # Converter outros erros para MessageParsingError
            parsing_error = MessageParsingError(
                f"Erro interno ao processar mensagem: {str(e)}",
                raw_data=raw_data,
                connection_id=connection_id
            )
            
            # Log e métricas
            websocket_logger.error_occurred(
                connection_id=connection_id,
                error_type=type(parsing_error).__name__,
                error_code=parsing_error.error_code,
                error_message=parsing_error.message,
                severity=parsing_error.severity.value
            )
            
            performance_monitor.record_error(
                connection_id=connection_id,
                error_type=type(parsing_error).__name__,
                error_code=parsing_error.error_code,
                severity=parsing_error.severity.value
            )
            
            raise parsing_error
    
    async def _handle_text_message(self, connection_id: str, message: TextMessage, start_time: float) -> None:
        """
        Processa mensagens de texto com tratamento de erros.
        
        Args:
            connection_id: ID único da conexão
            message: Mensagem de texto estruturada
            start_time: Timestamp de início do processamento
        """
        try:
            logger.info(f"Mensagem de texto recebida (ID: {connection_id}): {message.text}")
            
            processing_time = int((time.time() - start_time) * 1000)
            
            response = self.protocol.create_response_message(
                message=f"Echo: {message.text}",
                connection_id=connection_id,
                original_message=message.text,
                processing_time_ms=processing_time
            )
            
            await self._send_structured_message(connection_id, response, processing_time)
            
        except Exception as e:
            raise MessageParsingError(
                f"Erro ao processar mensagem de texto: {str(e)}",
                connection_id=connection_id
            )
    
    async def _handle_audio_message(self, connection_id: str, message: AudioDataMessage, start_time: float) -> None:
        """
        Processa mensagens de áudio com tratamento robusto de erros.
        
        Args:
            connection_id: ID único da conexão
            message: Mensagem de áudio estruturada
            start_time: Timestamp de início do processamento
        """
        try:
            # Decodificar dados de áudio
            audio_bytes = self.protocol.decode_audio_data(message)
            audio_size = len(audio_bytes)
            
            logger.info(f"Dados de áudio recebidos (ID: {connection_id}): {audio_size} bytes, formato: {message.format}")
            
            processing_time = int((time.time() - start_time) * 1000)
            
            # Registrar métricas específicas de áudio
            performance_monitor.record_metric(
                MetricType.MESSAGE,
                "audio.size_bytes",
                audio_size,
                tags={"connection_id": connection_id, "format": str(message.format)}
            )
            
            response = AudioReceivedMessage(
                size_bytes=audio_size,
                format=message.format,
                message=f"Áudio recebido: {audio_size} bytes",
                connection_id=connection_id,
                processing_time_ms=processing_time
            )
            
            await self._send_structured_message(connection_id, response, processing_time)
            
        except ValueError as e:
            # Erro de validação de áudio
            raise AudioProcessingError(
                str(e),
                audio_format=str(message.format),
                connection_id=connection_id
            )
        except Exception as e:
            # Outros erros de processamento de áudio
            raise AudioProcessingError(
                f"Erro interno ao processar áudio: {str(e)}",
                audio_format=str(message.format),
                connection_id=connection_id
            )
    
    async def _handle_broadcast_request(self, connection_id: str, message: BroadcastRequestMessage) -> None:
        """
        Processa solicitações de broadcast com tratamento de erros.
        
        Args:
            connection_id: ID único da conexão que solicita o broadcast
            message: Mensagem de solicitação de broadcast
        """
        try:
            logger.info(f"Broadcast solicitado (ID: {connection_id}): {message.message}")
            
            # Preparar mensagem de broadcast
            broadcast_msg = BroadcastMessage(
                message=message.message,
                sender_id=connection_id,
                connection_id=None  # Será definido individualmente para cada destinatário
            )
            
            # Determinar exclusões
            exclude_list = []
            if message.exclude_sender:
                exclude_list.append(connection_id)
            
            # Executar broadcast
            if message.target_connections:
                # Broadcast para conexões específicas
                success_count = 0
                failed_count = 0
                
                for target_id in message.target_connections:
                    if target_id not in exclude_list:
                        broadcast_msg.connection_id = target_id
                        success = await self.connection_manager.send_to_connection(
                            target_id, self.protocol.serialize_message(broadcast_msg)
                        )
                        if success:
                            success_count += 1
                        else:
                            failed_count += 1
            else:
                # Broadcast para todas as conexões
                total_connections = self.connection_manager.get_connection_count()
                success_count = await self.connection_manager.broadcast_message(
                    self.protocol.serialize_message(broadcast_msg), exclude_list
                )
                failed_count = max(0, total_connections - len(exclude_list) - success_count)
            
            # Log do broadcast
            websocket_logger.broadcast_sent(
                sender_id=connection_id,
                recipients_count=success_count,
                failed_count=failed_count,
                message_preview=message.message[:50]
            )
            
            # Registrar métricas de broadcast
            performance_monitor.record_metric(
                MetricType.MESSAGE,
                "broadcast.sent",
                1,
                tags={"sender_id": connection_id},
                metadata={"recipients": success_count, "failed": failed_count}
            )
            
            # Verificar se houve muitas falhas
            if failed_count > success_count:
                raise BroadcastError(
                    f"Broadcast falhou para a maioria das conexões",
                    failed_connections=failed_count,
                    total_connections=success_count + failed_count,
                    connection_id=connection_id
                )
            
            # Confirmar para o remetente
            confirmation = BroadcastConfirmationMessage(
                message=f"Broadcast enviado para {success_count} conexões",
                recipients_count=success_count,
                failed_count=failed_count,
                connection_id=connection_id
            )
            
            await self._send_structured_message(connection_id, confirmation)
            
        except BroadcastError:
            # Re-raise BroadcastError
            raise
        except Exception as e:
            # Converter outros erros
            raise BroadcastError(
                f"Erro interno no broadcast: {str(e)}",
                connection_id=connection_id
            )
    
    async def _handle_connection_info_request(self, connection_id: str, message: ConnectionInfoRequestMessage) -> None:
        """
        Processa solicitações de informação de conexão.
        
        Args:
            connection_id: ID da conexão solicitante
            message: Mensagem de solicitação de informações
        """
        conn_info = self.connection_manager.get_connection_info(connection_id)
        if not conn_info:
            raise ConnectionError(
                "Informações da conexão não encontradas",
                connection_id=connection_id
            )
        
        response = ConnectionInfoMessage(
            total_connections=self.connection_manager.get_connection_count(),
            your_connection_id=connection_id,
            connected_at=conn_info["connected_at"],
            message_count=conn_info["message_count"],
            last_activity=conn_info["last_activity"],
            connection_id=connection_id
        )
        
        await self._send_structured_message(connection_id, response)
    
    async def _handle_ping_message(self, connection_id: str, message: PingMessage) -> None:
        """
        Processa mensagens de ping.
        
        Args:
            connection_id: ID da conexão
            message: Mensagem de ping
        """
        logger.debug(f"Ping recebido (ID: {connection_id})")
        
        pong = PongMessage(
            data=message.data,
            connection_id=connection_id
        )
        
        await self._send_structured_message(connection_id, pong)
    
    async def _send_structured_message(self, connection_id: str, message: BaseMessage, 
                                     processing_time: Optional[float] = None) -> None:
        """
        Envia uma mensagem estruturada para uma conexão com recuperação.
        
        Args:
            connection_id: ID da conexão de destino
            message: Mensagem estruturada a ser enviada
            processing_time: Tempo de processamento em ms (opcional)
        """
        # Verificar se a conexão ainda está ativa antes de tentar enviar
        if not self.connection_manager.is_connection_active(connection_id):
            logger.debug(f"Conexão {connection_id} não está ativa, não enviando mensagem {message.type}")
            return
        
        async def send_operation():
            # Verificar novamente dentro da operação
            if not self.connection_manager.is_connection_active(connection_id):
                logger.debug(f"Conexão {connection_id} foi fechada durante envio")
                return False
                
            serialized = self.protocol.serialize_message(message)
            message_size = len(json.dumps(serialized).encode('utf-8'))
            
            success = await self.connection_manager.send_to_connection(connection_id, serialized)
            if not success:
                # Verificar se falha foi por desconexão (não deve usar recovery)
                if not self.connection_manager.is_connection_active(connection_id):
                    logger.debug(f"Falha no envio para {connection_id}: conexão não ativa")
                    return False
                    
                raise ConnectionError(
                    "Falha ao enviar mensagem para conexão",
                    connection_id=connection_id
                )
            
            # Log e métricas de mensagem enviada
            websocket_logger.message_sent(
                connection_id=connection_id,
                message_type=str(message.type),
                size_bytes=message_size,
                processing_time_ms=processing_time
            )
            
            performance_monitor.record_message_sent(
                connection_id=connection_id,
                message_type=str(message.type),
                size_bytes=message_size,
                processing_time=processing_time
            )
            
            return success
        
        try:
            await self.error_recovery.execute_with_recovery(
                operation=send_operation,
                connection_id=connection_id,
                error_context={"operation": "send_message", "message_type": message.type}
            )
        except Exception as e:
            # Se erro for relacionado à desconexão, não logar como erro crítico
            error_message = str(e).lower()
            if any(keyword in error_message for keyword in ["disconnect", "closed", "connection"]):
                logger.debug(f"Erro de desconexão ao enviar mensagem para {connection_id}: {e}")
            else:
                logger.error(f"Erro ao enviar mensagem para {connection_id}: {e}")
                raise
    
    async def _send_error_message(self, connection_id: str, error_code: str, error_message: str) -> None:
        """
        Envia uma mensagem de erro padronizada.
        
        Args:
            connection_id: ID da conexão
            error_code: Código do erro
            error_message: Mensagem de erro
        """
        try:
            error_msg = self.protocol.create_error_message(
                error_code=error_code,
                message=error_message,
                connection_id=connection_id
            )
            await self._send_structured_message(connection_id, error_msg)
        except Exception as e:
            logger.error(f"Falha ao enviar mensagem de erro para {connection_id}: {e}")
            websocket_logger.error(
                f"Falha ao enviar mensagem de erro para {connection_id}: {e}",
                connection_id=connection_id,
                original_error_code=error_code,
                original_error_message=error_message
            )
    
    async def _on_circuit_opened(self) -> None:
        """Callback chamado quando circuit breaker é aberto"""
        logger.critical("Circuit breaker ABERTO - sistema em modo de proteção")
        websocket_logger.circuit_breaker_event(
            event="opened",
            state=self.error_recovery.circuit_state.value,
            failure_count=self.error_recovery.failure_count
        )
    
    async def _on_circuit_closed(self) -> None:
        """Callback chamado quando circuit breaker é fechado"""
        logger.info("Circuit breaker FECHADO - sistema recuperado")
        websocket_logger.circuit_breaker_event(
            event="closed",
            state=self.error_recovery.circuit_state.value,
            failure_count=0
        )
    
    async def _on_critical_error(self, error: WebSocketError) -> None:
        """Callback chamado para erros críticos"""
        logger.critical(f"Erro crítico detectado: {error.error_code} - {error.message}")
        websocket_logger.circuit_breaker_event(
            event="critical_error",
            state=self.error_recovery.circuit_state.value,
            failure_count=self.error_recovery.failure_count,
            error_code=error.error_code,
            error_message=error.message
        )
    
    def _get_current_timestamp(self) -> str:
        """
        Retorna o timestamp atual em formato ISO.
        
        Returns:
            String com timestamp atual
        """
        from datetime import datetime
        return datetime.utcnow().isoformat() + "Z"
    
    def get_connection_count(self) -> int:
        """
        Retorna o número atual de conexões ativas.
        
        Returns:
            Número de conexões ativas
        """
        return self.connection_manager.get_connection_count()
    
    def get_connection_manager(self) -> ConnectionManager:
        """
        Retorna a instância do ConnectionManager para acesso direto.
        
        Returns:
            ConnectionManager: Instância do gerenciador de conexões
        """
        return self.connection_manager
    
    def get_message_protocol(self) -> MessageProtocol:
        """
        Retorna a instância do MessageProtocol para acesso direto.
        
        Returns:
            MessageProtocol: Instância do protocolo de mensagens
        """
        return self.protocol
    
    def get_error_recovery(self) -> ErrorRecoveryManager:
        """
        Retorna a instância do ErrorRecoveryManager para acesso direto.
        
        Returns:
            ErrorRecoveryManager: Instância do gerenciador de recuperação de erros
        """
        return self.error_recovery
    
    def get_performance_monitor(self):
        """
        Retorna a instância do PerformanceMonitor para acesso direto.
        
        Returns:
            PerformanceMonitor: Instância global do monitor de performance
        """
        return performance_monitor

    async def _process_audio_data(self, websocket: WebSocket, connection_id: str, audio_bytes: bytes) -> None:
        """
        Processa dados de áudio binários recebidos do frontend.
        
        Args:
            websocket: Instância do WebSocket
            connection_id: ID único da conexão
            audio_bytes: Dados de áudio em formato binário (PCM)
        """
        start_time = time.time()
        audio_size = len(audio_bytes)
        
        try:
            # Verificar se a conexão ainda está ativa
            if not self.connection_manager.is_connection_active(connection_id):
                logger.debug(f"Conexão {connection_id} já foi fechada, ignorando dados de áudio")
                return
            
            logger.info(f"Dados de áudio recebidos (ID: {connection_id}): {audio_size} bytes")
            
            # Log de áudio recebido
            websocket_logger.message_received(
                connection_id=connection_id,
                message_type="audio_binary",
                size_bytes=audio_size
            )
            
            # Registrar métrica de áudio recebido
            performance_monitor.record_message_received(
                connection_id=connection_id,
                message_type="audio_binary", 
                size_bytes=audio_size
            )
            
            processing_time = int((time.time() - start_time) * 1000)
            
            # Registrar métrica específica de áudio
            performance_monitor.record_metric(
                MetricType.MESSAGE,
                "audio.size_bytes",
                audio_size,
                tags={"connection_id": connection_id, "format": "pcm_binary"}
            )
            
            # Verificar novamente se a conexão ainda está ativa antes de enviar resposta
            if not self.connection_manager.is_connection_active(connection_id):
                logger.debug(f"Conexão {connection_id} foi fechada durante processamento, não enviando resposta")
                return
            
            # Enviar confirmação de recebimento APENAS se a conexão ainda estiver ativa
            try:
                from .message_protocol import AudioReceivedMessage, AudioFormat
                response = AudioReceivedMessage(
                    size_bytes=audio_size,
                    format=AudioFormat.PCM_16_16000,
                    message=f"Áudio recebido: {audio_size} bytes",
                    connection_id=connection_id,
                    processing_time_ms=processing_time
                )
                
                await self._send_structured_message(connection_id, response, processing_time)
                
            except Exception as send_error:
                # Se falhar ao enviar resposta, apenas log (não é crítico para dados de áudio)
                logger.debug(f"Falha ao enviar confirmação de áudio para {connection_id}: {send_error}")
            
            # TODO: Aqui você pode integrar com o Gemini Live API
            # Por exemplo:
            # gemini_response = await gemini_client.process_audio_chunk(audio_bytes)
            # await self._send_gemini_response(connection_id, gemini_response)
            
        except Exception as e:
            logger.error(f"Erro ao processar áudio: {e}")
            from .exceptions import AudioProcessingError
            raise AudioProcessingError(
                f"Erro interno ao processar áudio: {str(e)}",
                audio_format="pcm_binary",
                audio_size=audio_size,
                connection_id=connection_id
            ) 