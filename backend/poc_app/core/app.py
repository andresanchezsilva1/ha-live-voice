"""
Core application module for the Gemini Home Assistant POC.
This module contains the main application class that manages Gemini Live API 
integration with Home Assistant.
"""

import asyncio
import json
import time
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import logging
from uuid import uuid4

from ..gemini_client.gemini_live_api_client import GeminiLiveAPIClient
from ..ha_client.client import HomeAssistantClient
from ..exceptions.custom_exceptions import (
    SessionNotFoundError, 
    SessionCreationError, 
    AudioProcessingError,
    HomeAssistantError,
    IntegrationError
)
from ..ha_client.config import HAClientConfig
from ..gemini_client import HA_FUNCTION_DECLARATIONS
# Audio converter imports removed - now using raw PCM streaming
from .structured_logger import WebSocketLogger


class SessionData:
    """Container for session-specific data with enhanced monitoring"""
    
    def __init__(self, gemini_session: Any, created_at: datetime):
        self.gemini_session = gemini_session
        self.created_at = created_at
        self.last_activity = created_at
        self.audio_chunks_processed = 0
        self.function_calls_made = 0
        
        # Enhanced metrics
        self.total_audio_bytes = 0
        self.total_response_time = 0.0
        self.response_count = 0
        self.error_count = 0
        self.last_error: Optional[str] = None
        self.peak_memory_usage = 0
        self.connection_retries = 0
        self.is_healthy = True
        self.health_check_failures = 0
        
        # Resource tracking
        self.audio_buffer_size = 0
        self.pending_responses = 0
        
    def update_activity(self):
        """Update the last activity timestamp"""
        self.last_activity = datetime.now()
        
    def increment_audio_chunks(self, chunk_size: int = 0):
        """Increment the counter of processed audio chunks"""
        self.audio_chunks_processed += 1
        self.total_audio_bytes += chunk_size
        
    def increment_function_calls(self):
        """Increment the counter of function calls made"""
        self.function_calls_made += 1
        
    def record_response_time(self, response_time: float):
        """Record response time for performance tracking"""
        self.total_response_time += response_time
        self.response_count += 1
        
    def record_error(self, error_message: str):
        """Record an error for this session"""
        self.error_count += 1
        self.last_error = error_message
        self.health_check_failures += 1
        
        # Mark as unhealthy if too many errors
        if self.health_check_failures >= 3:
            self.is_healthy = False
            
    def record_connection_retry(self):
        """Record a connection retry attempt"""
        self.connection_retries += 1
        
    def update_memory_usage(self, current_usage: int):
        """Update peak memory usage tracking"""
        self.peak_memory_usage = max(self.peak_memory_usage, current_usage)
        
    def get_average_response_time(self) -> float:
        """Get average response time for this session"""
        if self.response_count == 0:
            return 0.0
        return self.total_response_time / self.response_count
        
    def get_session_age_minutes(self) -> float:
        """Get session age in minutes"""
        return (datetime.now() - self.created_at).total_seconds() / 60
        
    def get_idle_time_minutes(self) -> float:
        """Get idle time since last activity in minutes"""
        return (datetime.now() - self.last_activity).total_seconds() / 60
        
    def get_health_score(self) -> float:
        """Calculate a health score (0-1) for this session"""
        if not self.is_healthy:
            return 0.0
            
        # Base score
        score = 1.0
        
        # Penalize for errors
        if self.audio_chunks_processed > 0:
            error_rate = self.error_count / self.audio_chunks_processed
            score -= min(error_rate * 0.5, 0.4)  # Max 40% penalty for errors
            
        # Penalize for connection retries
        if self.connection_retries > 0:
            retry_penalty = min(self.connection_retries * 0.1, 0.3)  # Max 30% penalty
            score -= retry_penalty
            
        # Penalize for slow responses
        avg_response = self.get_average_response_time()
        if avg_response > 5.0:  # Slow if > 5 seconds
            score -= min((avg_response - 5.0) * 0.05, 0.3)  # Max 30% penalty
            
        return max(score, 0.0)
        
    def should_cleanup(self, max_age_minutes: int, max_idle_minutes: int = None) -> bool:
        """Determine if this session should be cleaned up"""
        if max_idle_minutes is None:
            max_idle_minutes = max_age_minutes // 2  # Default to half of max age
            
        # Cleanup if too old
        if self.get_session_age_minutes() > max_age_minutes:
            return True
            
        # Cleanup if idle too long
        if self.get_idle_time_minutes() > max_idle_minutes:
            return True
            
        # Cleanup if unhealthy
        if not self.is_healthy:
            return True
            
        return False
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert session data to dictionary for serialization"""
        return {
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "audio_chunks_processed": self.audio_chunks_processed,
            "function_calls_made": self.function_calls_made,
            "total_audio_bytes": self.total_audio_bytes,
            "average_response_time": self.get_average_response_time(),
            "error_count": self.error_count,
            "last_error": self.last_error,
            "connection_retries": self.connection_retries,
            "is_healthy": self.is_healthy,
            "health_score": self.get_health_score(),
            "session_age_minutes": self.get_session_age_minutes(),
            "idle_time_minutes": self.get_idle_time_minutes(),
            "peak_memory_usage": self.peak_memory_usage
        }


class GeminiHomeAssistantApp:
    """
    Main application class that orchestrates the integration between
    Home Assistant client, Gemini Live API client, and session management.
    """
    
    def __init__(
        self,
        gemini_api_key: str,
        ha_url: str,
        ha_token: str,
        session_timeout_minutes: int = 10,
        cleanup_interval_seconds: int = 60
    ):
        """
        Initialize the application with required clients and configuration.
        
        Args:
            gemini_api_key: API key for Gemini Live API
            ha_url: Home Assistant instance URL
            ha_token: Home Assistant Long-Lived Access Token
            session_timeout_minutes: Session timeout in minutes
            cleanup_interval_seconds: Cleanup task interval in seconds
        """
        self.logger = WebSocketLogger("GeminiHomeAssistantApp")
        
        # Initialize clients
        try:
            self.gemini_client = GeminiLiveAPIClient(gemini_api_key, model="gemini-2.5-flash-preview-native-audio-dialog")
            ha_config = HAClientConfig(base_url=ha_url, access_token=ha_token)
            self.ha_client = HomeAssistantClient.from_config(ha_config)
            
            self.logger.info("Clients initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize clients: {str(e)}")
            raise IntegrationError(f"Client initialization failed: {str(e)}")
        
        # Session management
        self.active_sessions: Dict[str, SessionData] = {}
        self.session_timeout_minutes = session_timeout_minutes
        self.cleanup_interval_seconds = cleanup_interval_seconds
        self._cleanup_task: Optional[asyncio.Task] = None
        
        self.logger.info(
            "GeminiHomeAssistantApp initialized",
            session_timeout_minutes=session_timeout_minutes,
            cleanup_interval_seconds=cleanup_interval_seconds
        )
    
    async def start(self):
        """Start the application and background tasks"""
        self.logger.info("Starting GeminiHomeAssistantApp")
        
        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._session_cleanup_task())
        
        self.logger.info("Background tasks started")
    
    async def stop(self):
        """Stop the application and cleanup resources"""
        self.logger.info("Stopping GeminiHomeAssistantApp")
        
        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Close all active sessions
        for session_id in list(self.active_sessions.keys()):
            await self.close_session(session_id)
        
        self.logger.info("GeminiHomeAssistantApp stopped")
    
    async def create_session(self, session_id: Optional[str] = None) -> str:
        """
        Create a new session with Gemini Live API.
        
        Args:
            session_id: Optional custom session ID, generates UUID if not provided
            
        Returns:
            str: The session ID
            
        Raises:
            SessionCreationError: If session creation fails
        """
        if session_id is None:
            session_id = str(uuid4())
        
        if session_id in self.active_sessions:
            self.logger.warning(f"Session {session_id} already exists, replacing")
            await self.close_session(session_id)
        
        try:
            self.logger.info(f"Creating session {session_id}")
            
            # Configurar function declarations para o cliente oficial
            self.gemini_client.set_function_declarations(HA_FUNCTION_DECLARATIONS)
            
            # Usar o método oficial da Live API para conectar
            system_instruction = "Você é um assistente de casa inteligente em português brasileiro. Responda de forma natural e amigável. Quando controlar dispositivos, forneça confirmações claras em português."
            
            # Conectar à Live API com configuração de áudio para interação por voz
            session_context = await self.gemini_client.connect_audio_session(
                system_instruction=system_instruction,
                voice_name="Aoede",
                language_code="pt-BR",
                enable_function_calling=True
            )
            
            # Entrar no context manager para obter a sessão ativa
            session = await session_context.__aenter__()
            
            # Armazenar dados da sessão com a sessão ativa
            session_data = SessionData(
                gemini_session=session,
                created_at=datetime.now()
            )
            self.active_sessions[session_id] = session_data
            
            # Também armazenar o context manager para fechamento adequado
            session_data._context_manager = session_context
            
            self.logger.info(
                f"Session {session_id} created successfully",
                session_id=session_id,
                total_active_sessions=len(self.active_sessions)
            )
            
            return session_id
            
        except Exception as e:
            self.logger.error(
                f"Failed to create session {session_id}: {str(e)}",
                session_id=session_id
            )
            raise SessionCreationError(f"Session creation failed: {str(e)}")
    
    async def process_audio(self, session_id: str, audio_chunk: bytes) -> Dict[str, Any]:
        """
        Process an audio chunk and return response.
        
        Args:
            session_id: The session ID
            audio_chunk: Audio data bytes
            
        Returns:
            Dict containing transcription, audio_response, and function_result
            
        Raises:
            SessionNotFoundError: If session doesn't exist
            AudioProcessingError: If audio processing fails
        """
        if session_id not in self.active_sessions:
            raise SessionNotFoundError(f"Session {session_id} not found")
        
        session_data = self.active_sessions[session_id]
        session_data.update_activity()
        session_data.increment_audio_chunks(len(audio_chunk))
        
        # Track processing start time
        start_time = time.time()
        
        try:
            self.logger.debug(
                f"Processing audio chunk for session {session_id}",
                session_id=session_id,
                audio_chunk_size=len(audio_chunk),
                chunks_processed=session_data.audio_chunks_processed,
                session_health_score=session_data.get_health_score()
            )
            
            # Verificar se cliente está conectado
            if not self.gemini_client.is_connected:
                self.logger.warning(f"Session {session_id} not connected, attempting to reconnect")
                session_data.record_connection_retry()
                
                error_msg = "Gemini client not connected"
                session_data.record_error(error_msg)
                raise AudioProcessingError(error_msg)
            
            # Log connection and session status
            self.logger.info(f"🔗 [CONNECTION-STATUS] Gemini connected: {self.gemini_client.is_connected}, Session active: {session_data.gemini_session is not None}")
            
            # Definir a sessão ativa no cliente
            self.gemini_client.session = session_data.gemini_session
            
            # Enviar áudio usando a API oficial
            await self.gemini_client.send_audio_data(audio_chunk)
            
            # Inicializar resultado
            result = {
                "transcription": "",
                "audio_response": None,
                "function_result": None,
                "session_metrics": {
                    "health_score": session_data.get_health_score(),
                    "total_chunks": session_data.audio_chunks_processed,
                    "total_audio_mb": round(session_data.total_audio_bytes / (1024 * 1024), 2),
                    "avg_response_time": session_data.get_average_response_time(),
                    "error_count": session_data.error_count
                }
            }
            
            # Coletar respostas usando o método oficial
            try:
                timeout_task = asyncio.create_task(asyncio.sleep(3.0))
                response_task = asyncio.create_task(self._collect_official_responses(session_data.gemini_session))
                
                done, pending = await asyncio.wait(
                    [timeout_task, response_task], 
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Cancelar tasks pendentes
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                
                # Verificar se tivemos timeout ou resposta
                if response_task in done:
                    responses = await response_task
                    for response in responses:
                        # Processar transcrição
                        if response.get("type") == "transcription":
                            result["transcription"] = response["data"]
                            self.logger.debug(
                                f"Transcription received",
                                session_id=session_id,
                                transcription=response["data"]
                            )
                        
                        # Processar function calls
                        if response.get("type") == "function_call":
                            function_calls = response["data"]["function_calls"]
                            for function_call in function_calls:
                                try:
                                    # Executar function call via Home Assistant
                                    function_result = await self._execute_function_call(
                                        function_call, session_data
                                    )
                                    
                                    if function_result:
                                        result["function_result"] = function_result
                                        session_data.increment_function_calls()
                                        
                                        self.logger.info(
                                            f"Function call executed",
                                            session_id=session_id,
                                            function_calls_made=session_data.function_calls_made,
                                            function_result=function_result
                                        )
                                
                                except Exception as e:
                                    error_msg = f"Error executing function call: {e}"
                                    session_data.record_error(error_msg)
                                    self.logger.error(error_msg)
                        
                        # Processar áudio de resposta
                        if response.get("type") == "audio":
                            result["audio_response"] = response["data"]
                            self.logger.debug(
                                f"Audio response generated",
                                session_id=session_id,
                                audio_response_size=len(response["data"])
                            )
                else:
                    self.logger.debug(f"Timeout waiting for Live API response (session {session_id})")
                    
            except Exception as e:
                error_msg = f"Error collecting Live API responses: {e}"
                session_data.record_error(error_msg)
                self.logger.debug(error_msg)
                # Não é necessariamente um erro fatal
            
            # Record response time
            processing_time = time.time() - start_time
            session_data.record_response_time(processing_time)
            
            return result
            
        except Exception as e:
            processing_time = time.time() - start_time
            session_data.record_response_time(processing_time)
            
            error_msg = f"Failed to process audio for session {session_id}: {str(e)}"
            session_data.record_error(str(e))
            
            self.logger.error(
                error_msg,
                session_id=session_id,
                processing_time=processing_time,
                session_health_score=session_data.get_health_score()
            )
            raise AudioProcessingError(f"Audio processing failed: {str(e)}")
    
    async def _send_audio_chunk_async(self, websocket, audio_data: bytes, chunk_id: str, chunk_count: int):
        """Send audio chunk via WebSocket asynchronously"""
        try:
            # Create chunk metadata
            chunk_metadata = {
                "type": "audio_chunk",
                "size": len(audio_data),
                "format": "pcm",
                "sample_rate": 24000,
                "channels": 1,
                "bits_per_sample": 16,
                "streaming": True,
                "timestamp": time.time(),
                "chunk_id": chunk_id,
                "chunk_count": chunk_count
            }
            
            # Send metadata first
            await websocket.send_text(json.dumps(chunk_metadata))
            
            # Send binary audio data
            await websocket.send_bytes(audio_data)
            
            self.logger.info(f"🎵 [BACKEND-SENT] {chunk_id} successfully sent {len(audio_data)} bytes to WebSocket")
        except Exception as e:
            self.logger.warning(f"Failed to send audio chunk {chunk_id} via WebSocket: {e}")
            raise

    async def _collect_official_responses(self, session_context, websocket=None) -> List[Dict[str, Any]]:
        """
        Collect responses from Gemini Live API using official client
        
        Args:
            session_context: The session context manager
            websocket: Optional WebSocket connection for streaming audio chunks
            
        Returns:
            List of response dictionaries
        """
        responses = []
        
        # Configurar callbacks para processar respostas
        collected_text = []
        collected_audio = []
        function_calls = []
        
        def text_callback(text: str):
            collected_text.append(text)
            
        def audio_callback(audio_data: bytes):
            # New streaming approach: send RAW PCM chunks immediately (no WAV conversion per chunk)
            chunk_id = f"chunk_{int(time.time() * 1000)}_{len(collected_audio)}"
            self.logger.info(f"🎵 [AUDIO-CALLBACK] {chunk_id} triggered with {len(audio_data)} bytes PCM, websocket available: {websocket is not None}")
            
            # Always collect audio for completion tracking
            collected_audio.append(audio_data)
            
            if websocket:
                try:
                    # Create chunk metadata
                    chunk_metadata = {
                        "type": "audio_chunk",
                        "size": len(audio_data),
                        "format": "pcm",
                        "sample_rate": 24000,
                        "channels": 1,
                        "bits_per_sample": 16,
                        "streaming": True,
                        "timestamp": time.time(),
                        "chunk_id": chunk_id,
                        "chunk_count": len(collected_audio)
                    }
                    
                    # Send metadata and binary data
                    self.logger.info(f"🎵 [BACKEND-SEND] {chunk_id} sending {len(audio_data)} raw PCM bytes")
                    asyncio.create_task(websocket.send_text(json.dumps(chunk_metadata)))
                    asyncio.create_task(websocket.send_bytes(audio_data))
                    self.logger.info(f"🎵 [BACKEND-SENT] {chunk_id} successfully sent {len(audio_data)} bytes to WebSocket")
                    
                except Exception as e:
                    self.logger.warning(f"Failed to send audio chunk via WebSocket: {e}")
                    # Audio is already in collected_audio for completion tracking
        
        def function_call_callback(calls):
            function_calls.extend(calls)
        
        # Receber respostas usando a API oficial
        try:
            # Definir a sessão no cliente se necessário
            self.gemini_client.session = session_context
            
            self.logger.debug(f"Starting to receive responses for up to 15 seconds...")
            
            # Usar timeout para evitar bloqueio indefinido
            await asyncio.wait_for(
                self.gemini_client.receive_responses(
                    text_callback=text_callback,
                    audio_callback=audio_callback,
                    function_call_callback=function_call_callback
                ),
                timeout=8.0  # Increased timeout to allow more time for audio generation and response processing
            )
        except asyncio.TimeoutError:
            self.logger.debug("Response collection timeout - proceeding with collected data")
        except Exception as e:
            self.logger.warning(f"Error collecting responses: {e}")
        
        # Processar texto coletado
        if collected_text:
            responses.append({
                "type": "text",
                "content": "".join(collected_text)
            })
        
        # Audio is now sent via streaming chunks, no need for consolidation
        # Just log summary of what was collected
        if collected_audio:
            total_audio_size = sum(len(chunk) for chunk in collected_audio)
            self.logger.info(f"📊 [AUDIO-SUMMARY] Streamed {len(collected_audio)} chunks, total: {total_audio_size} bytes PCM")
            
            # Send final streaming signal to indicate audio response is complete
            if websocket:
                try:
                    # Send audio complete signal via websocket
                    complete_message = {
                        "type": "audio_complete",
                        "chunks_sent": len(collected_audio),
                        "total_size": total_audio_size,
                        "format": "pcm",
                        "timestamp": time.time()
                    }
                    asyncio.create_task(websocket.send_text(json.dumps(complete_message)))
                    self.logger.info(f"🎵 [AUDIO-COMPLETE] Sent completion signal via websocket")
                except Exception as e:
                    self.logger.warning(f"Failed to send audio_complete via websocket: {e}")
            
            # Always add to responses for consistency
            responses.append({
                "type": "audio_complete",
                "chunks_sent": len(collected_audio),
                "total_size": total_audio_size,
                "format": "pcm"
            })
        else:
            self.logger.warning("🎵 [AUDIO-SUMMARY] No audio chunks were collected during response processing")
        
        # Processar chamadas de função
        if function_calls:
            responses.append({
                "type": "function_call",
                "data": {
                    "function_calls": [
                        {
                            "id": getattr(call, 'id', ''),
                            "name": getattr(call, 'name', ''),
                            "args": getattr(call, 'args', {})
                        } for call in function_calls
                    ]
                }
            })
        
        return responses
    
    async def _execute_function_call(self, function_call: Dict[str, Any], session_data: SessionData) -> Optional[Dict[str, Any]]:
        """
        Execute a function call via Home Assistant.
        
        Args:
            function_call: Function call data from Gemini
            session_data: Session data for logging
            
        Returns:
            Function execution result
        """
        try:
            function_name = function_call["name"]
            function_args = function_call.get("args", {})
            
            self.logger.info(f"Executing function: {function_name} with args: {function_args}")
            
            # Map function calls to Home Assistant actions
            if function_name == "turn_on_device":
                entity_id = function_args.get("entity_id")
                if entity_id:
                    await self.ha_client.turn_on(entity_id)
                    return {
                        "success": True,
                        "action": "turn_on",
                        "device": entity_id,
                        "message": f"Device {entity_id} turned on successfully"
                    }
            
            elif function_name == "turn_off_device":
                entity_id = function_args.get("entity_id")
                if entity_id:
                    await self.ha_client.turn_off(entity_id)
                    return {
                        "success": True,
                        "action": "turn_off",
                        "device": entity_id,
                        "message": f"Device {entity_id} turned off successfully"
                    }
            
            elif function_name == "get_device_state":
                entity_id = function_args.get("entity_id")
                if entity_id:
                    state = await self.ha_client.get_state(entity_id)
                    return {
                        "success": True,
                        "action": "get_state",
                        "device": entity_id,
                        "state": state.state if state else "unknown",
                        "message": f"Device {entity_id} state: {state.state if state else 'unknown'}"
                    }
            
            elif function_name == "list_devices":
                entities = await self.ha_client.get_entities()
                return {
                    "success": True,
                    "action": "list_devices",
                    "devices": [entity.entity_id for entity in entities[:10]],  # Limit to 10
                    "message": f"Found {len(entities)} devices"
                }
            
            else:
                self.logger.warning(f"Unknown function: {function_name}")
                return {
                    "success": False,
                    "error": f"Unknown function: {function_name}",
                    "message": f"Function {function_name} is not supported"
                }
                
        except Exception as e:
            self.logger.error(f"Error executing function {function_call}: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Error executing function: {str(e)}"
            }
    
    async def close_session(self, session_id: str) -> bool:
        """
        Close a session and cleanup resources.
        
        Args:
            session_id: The session ID to close
            
        Returns:
            bool: True if session was closed, False if not found
        """
        if session_id not in self.active_sessions:
            self.logger.warning(f"Attempted to close non-existent session {session_id}")
            return False
        
        try:
            session_data = self.active_sessions[session_id]
            
            # Fechar o context manager adequadamente
            if hasattr(session_data, '_context_manager'):
                try:
                    await session_data._context_manager.__aexit__(None, None, None)
                except Exception as e:
                    self.logger.warning(f"Error closing session context manager: {e}")
            
            # Remove from active sessions
            del self.active_sessions[session_id]
            
            self.logger.info(
                f"Session {session_id} closed",
                session_id=session_id,
                audio_chunks_processed=session_data.audio_chunks_processed,
                function_calls_made=session_data.function_calls_made,
                session_duration_minutes=(
                    datetime.now() - session_data.created_at
                ).total_seconds() / 60,
                remaining_active_sessions=len(self.active_sessions)
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                f"Error closing session {session_id}: {str(e)}",
                session_id=session_id
            )
            return False
    
    async def cleanup_old_sessions(self, max_age_minutes: Optional[int] = None, max_idle_minutes: Optional[int] = None) -> Dict[str, Any]:
        """
        Clean up sessions based on age, idle time, and health status.
        
        Args:
            max_age_minutes: Override default session timeout
            max_idle_minutes: Override default idle timeout
            
        Returns:
            Dict containing cleanup statistics
        """
        if max_age_minutes is None:
            max_age_minutes = self.session_timeout_minutes
        
        if max_idle_minutes is None:
            max_idle_minutes = max_age_minutes // 2  # Default to half of max age
        
        now = datetime.now()
        sessions_to_remove = []
        cleanup_reasons = {}
        
        # Analyze sessions for cleanup
        for session_id, session_data in self.active_sessions.items():
            cleanup_reason = None
            
            # Check various cleanup criteria
            if session_data.should_cleanup(max_age_minutes, max_idle_minutes):
                if session_data.get_session_age_minutes() > max_age_minutes:
                    cleanup_reason = "max_age_exceeded"
                elif session_data.get_idle_time_minutes() > max_idle_minutes:
                    cleanup_reason = "idle_timeout"
                elif not session_data.is_healthy:
                    cleanup_reason = "unhealthy_session"
                    
                sessions_to_remove.append(session_id)
                cleanup_reasons[session_id] = cleanup_reason
        
        # Perform cleanup
        cleanup_stats = {
            "sessions_cleaned": 0,
            "cleanup_reasons": {},
            "total_sessions_before": len(self.active_sessions),
            "total_sessions_after": 0,
            "cleanup_duration_seconds": 0,
            "memory_freed_mb": 0,
            "errors_during_cleanup": []
        }
        
        cleanup_start = time.time()
        
        for session_id in sessions_to_remove:
            try:
                session_data = self.active_sessions.get(session_id)
                if session_data:
                    # Calculate memory usage before cleanup
                    memory_before = session_data.peak_memory_usage
                    
                    # Close session
                    if await self.close_session(session_id):
                        cleanup_stats["sessions_cleaned"] += 1
                        cleanup_stats["memory_freed_mb"] += memory_before / (1024 * 1024)
                        
                        reason = cleanup_reasons.get(session_id, "unknown")
                        if reason not in cleanup_stats["cleanup_reasons"]:
                            cleanup_stats["cleanup_reasons"][reason] = 0
                        cleanup_stats["cleanup_reasons"][reason] += 1
                        
            except Exception as e:
                error_msg = f"Error cleaning up session {session_id}: {str(e)}"
                cleanup_stats["errors_during_cleanup"].append(error_msg)
                self.logger.error(error_msg)
        
        cleanup_stats["total_sessions_after"] = len(self.active_sessions)
        cleanup_stats["cleanup_duration_seconds"] = round(time.time() - cleanup_start, 3)
        
        if cleanup_stats["sessions_cleaned"] > 0:
            self.logger.info(
                f"Session cleanup completed",
                **cleanup_stats
            )
        
        return cleanup_stats
    
    async def _session_cleanup_task(self):
        """Background task for periodic session cleanup"""
        self.logger.info("Session cleanup task started")
        
        try:
            while True:
                await asyncio.sleep(self.cleanup_interval_seconds)
                await self.cleanup_old_sessions()
        except asyncio.CancelledError:
            self.logger.info("Session cleanup task cancelled")
            raise
        except Exception as e:
            self.logger.error(f"Session cleanup task error: {str(e)}")
    
    def get_session_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive statistics about active sessions.
        
        Returns:
            Dict containing detailed session statistics
        """
        if not self.active_sessions:
            return {
                "total_sessions": 0,
                "healthy_sessions": 0,
                "unhealthy_sessions": 0,
                "oldest_session_age_minutes": 0,
                "average_session_age_minutes": 0,
                "total_audio_chunks": 0,
                "total_function_calls": 0,
                "total_audio_mb": 0,
                "average_response_time": 0,
                "total_errors": 0,
                "total_connection_retries": 0,
                "average_health_score": 0,
                "sessions_by_health": {
                    "excellent": 0,  # > 0.8
                    "good": 0,       # 0.6 - 0.8
                    "fair": 0,       # 0.4 - 0.6
                    "poor": 0,       # 0.2 - 0.4
                    "critical": 0    # < 0.2
                },
                "memory_usage": {
                    "total_peak_mb": 0,
                    "average_peak_mb": 0,
                    "max_peak_mb": 0
                }
            }
        
        now = datetime.now()
        stats = {
            "total_sessions": len(self.active_sessions),
            "healthy_sessions": 0,
            "unhealthy_sessions": 0,
            "oldest_session_age_minutes": 0,
            "average_session_age_minutes": 0,
            "total_audio_chunks": 0,
            "total_function_calls": 0,
            "total_audio_mb": 0,
            "average_response_time": 0,
            "total_errors": 0,
            "total_connection_retries": 0,
            "average_health_score": 0,
            "sessions_by_health": {
                "excellent": 0,  # > 0.8
                "good": 0,       # 0.6 - 0.8
                "fair": 0,       # 0.4 - 0.6
                "poor": 0,       # 0.2 - 0.4
                "critical": 0    # < 0.2
            },
            "memory_usage": {
                "total_peak_mb": 0,
                "average_peak_mb": 0,
                "max_peak_mb": 0
            },
            "session_details": []
        }
        
        total_age = 0
        total_response_time = 0
        total_responses = 0
        total_health_score = 0
        total_peak_memory = 0
        max_peak_memory = 0
        
        for session_id, session_data in self.active_sessions.items():
            # Basic metrics
            age_minutes = session_data.get_session_age_minutes()
            health_score = session_data.get_health_score()
            
            total_age += age_minutes
            stats["oldest_session_age_minutes"] = max(stats["oldest_session_age_minutes"], age_minutes)
            stats["total_audio_chunks"] += session_data.audio_chunks_processed
            stats["total_function_calls"] += session_data.function_calls_made
            stats["total_audio_mb"] += session_data.total_audio_bytes / (1024 * 1024)
            stats["total_errors"] += session_data.error_count
            stats["total_connection_retries"] += session_data.connection_retries
            
            # Health tracking
            if session_data.is_healthy:
                stats["healthy_sessions"] += 1
            else:
                stats["unhealthy_sessions"] += 1
                
            total_health_score += health_score
            
            # Categorize by health score
            if health_score > 0.8:
                stats["sessions_by_health"]["excellent"] += 1
            elif health_score > 0.6:
                stats["sessions_by_health"]["good"] += 1
            elif health_score > 0.4:
                stats["sessions_by_health"]["fair"] += 1
            elif health_score > 0.2:
                stats["sessions_by_health"]["poor"] += 1
            else:
                stats["sessions_by_health"]["critical"] += 1
            
            # Response time tracking
            if session_data.response_count > 0:
                total_response_time += session_data.total_response_time
                total_responses += session_data.response_count
            
            # Memory tracking
            peak_memory_mb = session_data.peak_memory_usage / (1024 * 1024)
            total_peak_memory += peak_memory_mb
            max_peak_memory = max(max_peak_memory, peak_memory_mb)
            
            # Session details for debugging
            stats["session_details"].append({
                "session_id": session_id,
                "age_minutes": round(age_minutes, 2),
                "idle_minutes": round(session_data.get_idle_time_minutes(), 2),
                "health_score": round(health_score, 3),
                "is_healthy": session_data.is_healthy,
                "audio_chunks": session_data.audio_chunks_processed,
                "function_calls": session_data.function_calls_made,
                "errors": session_data.error_count,
                "last_error": session_data.last_error,
                "connection_retries": session_data.connection_retries,
                "avg_response_time": round(session_data.get_average_response_time(), 3),
                "peak_memory_mb": round(peak_memory_mb, 2)
            })
        
        # Calculate averages
        session_count = len(self.active_sessions)
        stats["average_session_age_minutes"] = round(total_age / session_count, 2)
        stats["average_health_score"] = round(total_health_score / session_count, 3)
        stats["total_audio_mb"] = round(stats["total_audio_mb"], 2)
        
        if total_responses > 0:
            stats["average_response_time"] = round(total_response_time / total_responses, 3)
        
        # Memory statistics
        stats["memory_usage"]["total_peak_mb"] = round(total_peak_memory, 2)
        stats["memory_usage"]["average_peak_mb"] = round(total_peak_memory / session_count, 2)
        stats["memory_usage"]["max_peak_mb"] = round(max_peak_memory, 2)
        
        return stats
    
    def is_session_active(self, session_id: str) -> bool:
        """Check if a session is active"""
        return session_id in self.active_sessions
        
    def get_session_health_report(self) -> Dict[str, Any]:
        """
        Generate a comprehensive health report for all sessions.
        
        Returns:
            Dict containing health analysis and recommendations
        """
        stats = self.get_session_stats()
        
        # Calculate health metrics
        total_sessions = stats["total_sessions"]
        if total_sessions == 0:
            return {
                "overall_health": "excellent",
                "health_score": 1.0,
                "recommendations": [],
                "alerts": [],
                "summary": "No active sessions"
            }
        
        healthy_ratio = stats["healthy_sessions"] / total_sessions
        avg_health_score = stats["average_health_score"]
        
        # Determine overall health
        if avg_health_score >= 0.8 and healthy_ratio >= 0.9:
            overall_health = "excellent"
        elif avg_health_score >= 0.6 and healthy_ratio >= 0.7:
            overall_health = "good"
        elif avg_health_score >= 0.4 and healthy_ratio >= 0.5:
            overall_health = "fair"
        elif avg_health_score >= 0.2 and healthy_ratio >= 0.3:
            overall_health = "poor"
        else:
            overall_health = "critical"
        
        # Generate recommendations
        recommendations = []
        alerts = []
        
        if stats["unhealthy_sessions"] > 0:
            alerts.append(f"{stats['unhealthy_sessions']} unhealthy sessions detected")
            recommendations.append("Consider cleaning up unhealthy sessions")
        
        if stats["total_errors"] > stats["total_audio_chunks"] * 0.1:  # > 10% error rate
            alerts.append("High error rate detected across sessions")
            recommendations.append("Investigate connection stability and error patterns")
        
        if stats["total_connection_retries"] > stats["total_sessions"] * 2:  # > 2 retries per session
            alerts.append("Frequent connection retries detected")
            recommendations.append("Check network connectivity and API stability")
        
        if stats["average_response_time"] > 5.0:
            alerts.append("Slow average response times detected")
            recommendations.append("Monitor system performance and API latency")
        
        if stats["sessions_by_health"]["critical"] > 0:
            alerts.append(f"{stats['sessions_by_health']['critical']} sessions in critical state")
            recommendations.append("Immediately investigate critical sessions")
        
        if stats["memory_usage"]["max_peak_mb"] > 100:  # > 100MB per session
            alerts.append("High memory usage detected in some sessions")
            recommendations.append("Monitor memory usage and consider session limits")
        
        return {
            "overall_health": overall_health,
            "health_score": round(avg_health_score, 3),
            "healthy_ratio": round(healthy_ratio, 3),
            "recommendations": recommendations,
            "alerts": alerts,
            "summary": f"{total_sessions} active sessions, {stats['healthy_sessions']} healthy",
            "detailed_stats": stats
        }
    
    async def force_cleanup_unhealthy_sessions(self) -> Dict[str, Any]:
        """
        Force cleanup of all unhealthy sessions regardless of age.
        
        Returns:
            Dict containing cleanup results
        """
        unhealthy_sessions = []
        
        for session_id, session_data in self.active_sessions.items():
            if not session_data.is_healthy:
                unhealthy_sessions.append(session_id)
        
        if not unhealthy_sessions:
            return {
                "sessions_cleaned": 0,
                "message": "No unhealthy sessions found"
            }
        
        cleanup_stats = {
            "sessions_cleaned": 0,
            "errors": [],
            "cleaned_sessions": []
        }
        
        for session_id in unhealthy_sessions:
            try:
                if await self.close_session(session_id):
                    cleanup_stats["sessions_cleaned"] += 1
                    cleanup_stats["cleaned_sessions"].append(session_id)
            except Exception as e:
                error_msg = f"Error cleaning unhealthy session {session_id}: {str(e)}"
                cleanup_stats["errors"].append(error_msg)
                self.logger.error(error_msg)
        
        self.logger.info(
            f"Force cleanup of unhealthy sessions completed",
            **cleanup_stats
        )
        
        return cleanup_stats
    
    def get_session_by_id(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific session.
        
        Args:
            session_id: The session ID to query
            
        Returns:
            Dict containing session details or None if not found
        """
        if session_id not in self.active_sessions:
            return None
        
        session_data = self.active_sessions[session_id]
        return {
            "session_id": session_id,
            **session_data.to_dict()
        }
    
    async def optimize_sessions(self) -> Dict[str, Any]:
        """
        Perform session optimization including cleanup and health checks.
        
        Returns:
            Dict containing optimization results
        """
        optimization_start = time.time()
        
        # Get initial stats
        initial_stats = self.get_session_stats()
        
        # Perform cleanup with more aggressive settings for optimization
        cleanup_results = await self.cleanup_old_sessions(
            max_age_minutes=self.session_timeout_minutes,
            max_idle_minutes=self.session_timeout_minutes // 3  # More aggressive idle timeout
        )
        
        # Force cleanup unhealthy sessions
        unhealthy_cleanup = await self.force_cleanup_unhealthy_sessions()
        
        # Get final stats
        final_stats = self.get_session_stats()
        
        optimization_results = {
            "optimization_duration_seconds": round(time.time() - optimization_start, 3),
            "initial_sessions": initial_stats["total_sessions"],
            "final_sessions": final_stats["total_sessions"],
            "sessions_removed": initial_stats["total_sessions"] - final_stats["total_sessions"],
            "cleanup_results": cleanup_results,
            "unhealthy_cleanup": unhealthy_cleanup,
            "health_improvement": {
                "initial_health_score": initial_stats.get("average_health_score", 0),
                "final_health_score": final_stats.get("average_health_score", 0),
                "initial_healthy_sessions": initial_stats.get("healthy_sessions", 0),
                "final_healthy_sessions": final_stats.get("healthy_sessions", 0)
            },
            "memory_freed_mb": cleanup_results.get("memory_freed_mb", 0)
        }
        
        self.logger.info(
            "Session optimization completed",
            **optimization_results
        )
        
        return optimization_results
    
    async def send_welcome_message_with_websocket(self, session_id: str, websocket) -> Dict[str, Any]:
        """
        Send a welcome message with WebSocket streaming support.
        
        Args:
            session_id: The session ID
            websocket: WebSocket connection for streaming audio chunks
            
        Returns:
            Dict containing welcome response and audio
            
        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        if session_id not in self.active_sessions:
            raise SessionNotFoundError(f"Session {session_id} not found")

        session_data = self.active_sessions[session_id]
        session_data.update_activity()

        try:
            self.logger.info(
                f"Sending welcome message with WebSocket streaming for session {session_id}",
                session_id=session_id
            )

            # Enviar mensagem de texto inicial para gerar resposta de boas-vindas
            welcome_prompt = "Olá! Dê as boas-vindas ao usuário ao Home Assistant. Seja breve e amigável, explicando que você pode ajudar a controlar dispositivos e responder perguntas sobre a casa."

            # Definir a sessão ativa no cliente
            self.gemini_client.session = session_data.gemini_session

            # Usar a API oficial para enviar mensagem de texto
            await self.gemini_client.send_text_message(welcome_prompt, turn_complete=True)

            # Inicializar resultado com fallback
            result = {
                "transcription": "",
                "response_text": "Olá! Bem-vindo ao assistente de voz do Home Assistant. Como posso ajudá-lo hoje?",
                "audio_response": None,
                "function_result": None,
                "streaming_complete": False,
                "chunks_sent": 0,
                "total_size": 0
            }

            # Tentar coletar resposta com timeout and WebSocket streaming
            try:
                timeout_task = asyncio.create_task(asyncio.sleep(5.0))  # Timeout maior para boas-vindas
                response_task = asyncio.create_task(self._collect_official_responses(session_data.gemini_session, websocket))

                done, pending = await asyncio.wait(
                    [timeout_task, response_task], 
                    return_when=asyncio.FIRST_COMPLETED
                )

                # Cancelar tasks pendentes
                for task in pending:
                    task.cancel()

                # Processar resposta se disponível
                if response_task in done:
                    responses = await response_task

                    for response in responses:
                        # Processar resposta de texto
                        if response.get("type") == "text":
                            result["response_text"] = response["content"]

                        # Processar áudio de resposta (legacy fallback)
                        if response.get("type") == "audio":
                            result["audio_response"] = response["data"]
                            self.logger.debug(
                                f"Welcome audio response generated",
                                session_id=session_id,
                                audio_response_size=len(response["data"])
                            )
                            
                        # Audio streaming complete signal
                        if response.get("type") == "audio_complete":
                            result["streaming_complete"] = True
                            result["chunks_sent"] = response.get("chunks_sent", 0)
                            result["total_size"] = response.get("total_size", 0)
                            self.logger.debug(
                                f"Welcome audio streaming completed",
                                session_id=session_id,
                                chunks_sent=response.get("chunks_sent", 0),
                                total_size=response.get("total_size", 0)
                            )
                            break  # Parar após completar streaming

            except Exception as e:
                self.logger.warning(f"Failed to get welcome response: {e}")
                # Manter resultado fallback

            self.logger.info(
                f"Welcome message sent for session {session_id}",
                session_id=session_id,
                has_audio_response=result["audio_response"] is not None,
                streaming_complete=result["streaming_complete"]
            )

            return result

        except Exception as e:
            self.logger.error(
                f"Failed to send welcome message for session {session_id}: {str(e)}",
                session_id=session_id
            )
            # Retornar resultado fallback em caso de erro
            return {
                "transcription": "",
                "response_text": "Olá! Bem-vindo ao assistente de voz do Home Assistant. Como posso ajudá-lo hoje?",
                "audio_response": None,
                "function_result": None,
                "streaming_complete": False,
                "chunks_sent": 0,
                "total_size": 0
            }

    async def send_welcome_message(self, session_id: str) -> Dict[str, Any]:
        """
        Send a welcome message to initialize the conversation with audio response.
        
        Args:
            session_id: The session ID
            
        Returns:
            Dict containing welcome response and audio
            
        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        if session_id not in self.active_sessions:
            raise SessionNotFoundError(f"Session {session_id} not found")
        
        session_data = self.active_sessions[session_id]
        session_data.update_activity()
        
        try:
            self.logger.info(
                f"Sending welcome message for session {session_id}",
                session_id=session_id
            )
            
            # Enviar mensagem de texto inicial para gerar resposta de boas-vindas
            welcome_prompt = "Olá! Dê as boas-vindas ao usuário ao Home Assistant. Seja breve e amigável, explicando que você pode ajudar a controlar dispositivos e responder perguntas sobre a casa."
            
            # Definir a sessão ativa no cliente
            self.gemini_client.session = session_data.gemini_session
            
            # Usar a API oficial para enviar mensagem de texto
            await self.gemini_client.send_text_message(welcome_prompt, turn_complete=True)
            
            # Inicializar resultado com fallback
            result = {
                "transcription": "",
                "response_text": "Olá! Bem-vindo ao assistente de voz do Home Assistant. Como posso ajudá-lo hoje?",
                "audio_response": None,
                "function_result": None
            }
            
            # Tentar coletar resposta com timeout
            try:
                timeout_task = asyncio.create_task(asyncio.sleep(5.0))  # Timeout maior para boas-vindas
                response_task = asyncio.create_task(self._collect_official_responses(session_data.gemini_session))
                
                done, pending = await asyncio.wait(
                    [timeout_task, response_task], 
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Cancelar tasks pendentes
                for task in pending:
                    task.cancel()
                
                # Processar resposta se disponível
                if response_task in done:
                    responses = await response_task
                    
                    for response in responses:
                        # Processar resposta de texto
                        if response.get("type") == "text":
                            result["response_text"] = response["content"]
                            
                        # Processar áudio de resposta
                        if response.get("type") == "audio":
                            result["audio_response"] = response["data"]
                            self.logger.debug(
                                f"Welcome audio response generated",
                                session_id=session_id,
                                audio_response_size=len(response["data"])
                            )
                            break  # Parar após receber áudio
                            
            except Exception as e:
                self.logger.warning(f"Failed to get welcome response: {e}")
                # Manter resultado fallback
            
            self.logger.info(
                f"Welcome message sent for session {session_id}",
                session_id=session_id,
                has_audio_response=result["audio_response"] is not None
            )
            
            return result
            
        except Exception as e:
            self.logger.error(
                f"Failed to send welcome message for session {session_id}: {str(e)}",
                session_id=session_id
            )
            # Retornar resultado fallback em caso de erro
            return {
                "transcription": "",
                "response_text": "Olá! Bem-vindo ao assistente de voz do Home Assistant. Como posso ajudá-lo hoje?",
                "audio_response": None,
                "function_result": None
            }
    
    async def process_audio_with_websocket(self, session_id: str, audio_chunk: bytes, websocket) -> Dict[str, Any]:
        """
        Process audio for a session with WebSocket streaming support.
        
        Args:
            session_id: Session ID for the request
            audio_chunk: Raw audio data (PCM format expected)
            websocket: WebSocket connection for streaming audio chunks
            
        Returns:
            Dict containing response information
            
        Raises:
            SessionNotFoundError: If session doesn't exist
            AudioProcessingError: If audio processing fails
        """
        if session_id not in self.active_sessions:
            raise SessionNotFoundError(f"Session {session_id} not found")
        
        session_data = self.active_sessions[session_id]
        session_data.update_activity()
        
        start_time = time.time()
        
        try:
            # Log audio processing
            self.logger.debug(
                f"Processing audio with WebSocket streaming",
                session_id=session_id,
                audio_size=len(audio_chunk)
            )
            
            # Update session metrics
            session_data.increment_audio_chunks(len(audio_chunk))
            
            # Verificar se cliente está conectado
            if not self.gemini_client.is_connected:
                self.logger.warning(f"Session {session_id} not connected, attempting to reconnect")
                session_data.record_connection_retry()
                
                error_msg = "Gemini client not connected"
                session_data.record_error(error_msg)
                raise AudioProcessingError(error_msg)
            
            # Log connection and session status
            self.logger.info(f"🔗 [CONNECTION-STATUS] Gemini connected: {self.gemini_client.is_connected}, Session active: {session_data.gemini_session is not None}")
            
            # Definir a sessão ativa no cliente
            self.gemini_client.session = session_data.gemini_session
            
            # Enviar áudio usando a API oficial (sem turn_complete, o Gemini detecta automaticamente)
            self.logger.info(f"🎙️ [AUDIO-SEND] Sending {len(audio_chunk)} bytes")
            await self.gemini_client.send_audio_data(audio_chunk)
            
            # Initialize result
            result = {
                "transcription": "",
                "response_text": "",
                "audio_response": None,
                "function_result": None,
                "session_id": session_id,
                "processing_time_ms": 0,
                "audio_chunks_processed": session_data.audio_chunks_processed,
                "error_count": session_data.error_count
            }
            
            # Coletar respostas usando o método oficial with WebSocket
            try:
                timeout_task = asyncio.create_task(asyncio.sleep(15.0))  # Increased timeout to match response collection timeout
                response_task = asyncio.create_task(self._collect_official_responses(session_data.gemini_session, websocket))
                
                done, pending = await asyncio.wait(
                    [timeout_task, response_task], 
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Cancelar tasks pendentes
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                
                # Verificar se tivemos timeout ou resposta
                if response_task in done:
                    responses = await response_task
                    for response in responses:
                        # Processar transcrição
                        if response.get("type") == "transcription":
                            result["transcription"] = response["data"]
                            self.logger.debug(
                                f"Transcription received",
                                session_id=session_id,
                                transcription=response["data"]
                            )
                        
                        # Processar function calls
                        if response.get("type") == "function_call":
                            function_calls = response["data"]["function_calls"]
                            for function_call in function_calls:
                                try:
                                    # Executar function call via Home Assistant
                                    function_result = await self._execute_function_call(
                                        function_call, session_data
                                    )
                                    
                                    if function_result:
                                        result["function_result"] = function_result
                                        session_data.increment_function_calls()
                                        
                                        self.logger.info(
                                            f"Function call executed",
                                            session_id=session_id,
                                            function_calls_made=session_data.function_calls_made,
                                            function_result=function_result
                                        )
                                
                                except Exception as e:
                                    error_msg = f"Error executing function call: {e}"
                                    session_data.record_error(error_msg)
                                    self.logger.error(error_msg)
                        
                        # Processar áudio de resposta (note: audio is now streamed via websocket)
                        if response.get("type") == "audio":
                            result["audio_response"] = response["data"]
                            self.logger.debug(
                                f"Audio response generated",
                                session_id=session_id,
                                audio_response_size=len(response["data"])
                            )
                        
                        # Audio streaming complete signal
                        if response.get("type") == "audio_complete":
                            result["streaming_complete"] = True
                            result["chunks_sent"] = response.get("chunks_sent", 0)
                            result["total_size"] = response.get("total_size", 0)
                            self.logger.debug(
                                f"Audio streaming completed",
                                session_id=session_id,
                                chunks_sent=response.get("chunks_sent", 0),
                                total_size=response.get("total_size", 0)
                            )
                else:
                    self.logger.debug(f"Timeout waiting for Live API response (session {session_id})")
                    
            except Exception as e:
                error_msg = f"Error collecting Live API responses: {e}"
                session_data.record_error(error_msg)
                self.logger.debug(error_msg)
                # Não é necessariamente um erro fatal
            
            # Record response time
            processing_time = time.time() - start_time
            session_data.record_response_time(processing_time)
            result["processing_time_ms"] = int(processing_time * 1000)
            
            return result
            
        except Exception as e:
            processing_time = time.time() - start_time
            session_data.record_response_time(processing_time)
            
            error_msg = f"Failed to process audio for session {session_id}: {str(e)}"
            session_data.record_error(str(e))
            
            self.logger.error(
                error_msg,
                session_id=session_id,
                processing_time=processing_time,
                session_health_score=session_data.get_health_score()
            )
            raise AudioProcessingError(f"Audio processing failed: {str(e)}") 