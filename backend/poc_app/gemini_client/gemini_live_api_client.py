#!/usr/bin/env python3
"""
Cliente Gemini Live API - Implementação oficial baseada na documentação
https://ai.google.dev/gemini-api/docs/live?hl=pt-br

Este cliente implementa o streaming de áudio bidirecional em tempo real
usando a Live API oficial do Gemini conforme a documentação.
"""

import asyncio
import logging
import json
import time
from typing import Any, Dict, List, Optional, Callable, Union
from google import genai
from google.genai import types
import numpy as np

logger = logging.getLogger(__name__)


class GeminiLiveAPIClient:
    """
    Cliente oficial da Live API do Gemini para streaming de áudio bidirecional
    
    Baseado na documentação oficial:
    https://ai.google.dev/gemini-api/docs/live?hl=pt-br
    """
    
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash-live-001"):
        """
        Inicializa o cliente da Live API
        
        Args:
            api_key: Chave da API do Google AI
            model: Modelo a ser usado (padrão: gemini-2.5-flash-preview-native-audio-dialog)
        """
        self.api_key = api_key
        self.model = model
        self.client = genai.Client(api_key=api_key)
        self.session = None
        self.is_connected = False
        self.function_declarations = []
        
        # Controle de estado para gravação manual
        self.is_recording = False
        
        # Controle de estado da sessão
        self.is_generating = False  # Se o Gemini está gerando resposta
        self.should_accept_audio = True  # Se deve aceitar novos áudios
        
        # Callback para notificar quando a geração estiver completa
        self._completion_callback = None
        
        logger.info(f"Cliente Live API inicializado - modelo: {model}")
    
    def set_function_declarations(self, function_declarations: List[Dict[str, Any]]):
        """
        Define as declarações de função para function calling
        
        Args:
            function_declarations: Lista de declarações de função
        """
        self.function_declarations = function_declarations
        logger.info(f"Configuradas {len(function_declarations)} declarações de função")
    
    def set_completion_callback(self, callback):
        """
        Define callback para ser executado quando a geração do Gemini terminar
        
        Args:
            callback: Função a ser executada quando generation_complete for recebido
        """
        self._completion_callback = callback
        logger.debug("Callback de completion configurado")
    
    async def connect_audio_session(
        self,
        system_instruction: Optional[str] = None,
        voice_name: str = "Kore",
        language_code: str = "pt-BR",
        enable_function_calling: bool = True
    ) -> Any:
        """
        Conecta à Live API com configuração para áudio e controle manual
        
        Args:
            system_instruction: Instruções do sistema
            voice_name: Nome da voz (Puck, Charon, Kore, Fenrir, Aoede, Leda, Orus, Zephyr)
            language_code: Código do idioma (pt-BR para português brasileiro)
            enable_function_calling: Se deve habilitar function calling
            
        Returns:
            Context manager da sessão ativa da Live API
        """
        try:
            # Configuração da sessão com VAD DESABILITADO para controle manual
            config = {
                "response_modalities": ["AUDIO"],
                "speech_config": {
                    "voice_config": {
                        "prebuilt_voice_config": {
                            "voice_name": voice_name
                        }
                    },
                    "language_code": language_code
                },
                # DESABILITAR VAD automático - controle manual via activity_start/end
                "realtime_input_config": {
                    "automatic_activity_detection": {
                        "disabled": True  # Usar controle manual
                    }
                }
            }
            
            # Adicionar system instruction se fornecido
            if system_instruction:
                config["system_instruction"] = system_instruction
            
            # Adicionar tools se function calling estiver habilitado
            if enable_function_calling and self.function_declarations:
                config["tools"] = [{"function_declarations": self.function_declarations}]
            
            # Conectar à Live API - retorna o context manager diretamente
            session_context = self.client.aio.live.connect(
                model=self.model,
                config=config
            )
            
            self.is_connected = True
            logger.info("Conectado à Live API com sucesso")
            logger.info(f"Configuração: voz={voice_name}, idioma={language_code}")
            
            return session_context
            
        except Exception as e:
            logger.error(f"Erro ao conectar à Live API: {e}")
            raise
    
    async def connect_text_session(
        self,
        system_instruction: Optional[str] = None,
        enable_function_calling: bool = True
    ) -> Any:
        """
        Conecta à Live API com configuração para texto
        
        Args:
            system_instruction: Instruções do sistema
            enable_function_calling: Se deve habilitar function calling
            
        Returns:
            Context manager da sessão ativa da Live API
        """
        try:
            # Configuração da sessão
            config = {
                "response_modalities": ["TEXT"]  # Resposta em texto
            }
            
            # Adicionar system instruction se fornecido
            if system_instruction:
                config["system_instruction"] = system_instruction
            
            # Adicionar tools se function calling estiver habilitado
            if enable_function_calling and self.function_declarations:
                config["tools"] = [{"function_declarations": self.function_declarations}]
            
            # Conectar à Live API - retorna o context manager diretamente
            session_context = self.client.aio.live.connect(
                model=self.model,
                config=config
            )
            
            self.is_connected = True
            logger.info("Conectado à Live API (modo texto) com sucesso")
            
            return session_context
            
        except Exception as e:
            logger.error(f"Erro ao conectar à Live API: {e}")
            raise
    
    async def send_text_message(self, message: str, turn_complete: bool = True):
        """
        Envia uma mensagem de texto
        
        Args:
            message: Texto da mensagem
            turn_complete: Se deve marcar o turno como completo
        """
        if not self.is_connected or not self.session:
            raise RuntimeError("Não conectado à Live API")
        
        try:
            await self.session.send_client_content(
                turns={"role": "user", "parts": [{"text": message}]},
                turn_complete=turn_complete
            )
            logger.info(f"Mensagem texto enviada: {message[:50]}...")
            
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem de texto: {e}")
            raise
    
    async def send_audio_data(
        self,
        audio_data: bytes,
        mime_type: str = "audio/pcm;rate=16000"
    ):
        """
        Envia dados de áudio em tempo real (controle manual) com retry
        
        Args:
            audio_data: Dados de áudio em bytes (16-bit PCM, 16kHz, mono)
            mime_type: Tipo MIME do áudio
        """
        if not self.is_connected or not self.session:
            raise RuntimeError("Não conectado à Live API")
        
        # Verificar se deve aceitar áudio
        if not self.should_accept_audio:
            logger.debug("Ignorando áudio - sessão não aceita novos dados")
            return
        
        try:
            # Enviar áudio diretamente (sem detecção de silêncio automático)
            await self.session.send_realtime_input(
                audio=types.Blob(data=audio_data, mime_type=mime_type)
            )
            logger.debug(f"🎵 [MANUAL-AUDIO] Dados de áudio enviados: {len(audio_data)} bytes")
            
        except Exception as e:
            # Log específico para keepalive timeout
            if "keepalive ping timeout" in str(e):
                logger.warning(f"⚠️ [KEEPALIVE-TIMEOUT] Conexão perdida - keepalive timeout. Marcando sessão como desconectada.")
                self.is_connected = False
                self.should_accept_audio = False
            else:
                logger.error(f"Erro ao enviar dados de áudio: {e}")
            raise
    
    async def start_recording(self):
        """
        Inicia uma atividade de gravação (controle manual)
        """
        if not self.is_connected or not self.session:
            raise RuntimeError("Não conectado à Live API")
        
        try:
            # Resetar estado
            self.should_accept_audio = True
            self.is_generating = False
            self.is_recording = True
            
            # Enviar activity_start conforme documentação
            await self.session.send_realtime_input(activity_start=types.ActivityStart())
            logger.info("🎙️ [MANUAL-START] Atividade de gravação iniciada")
            
        except Exception as e:
            logger.error(f"Erro ao iniciar gravação: {e}")
            raise
    
    async def stop_recording(self):
        """
        Para uma atividade de gravação e processa resposta (controle manual) com retry
        """
        if not self.is_connected or not self.session:
            raise RuntimeError("Não conectado à Live API")
        
        try:
            # Marcar que não aceita mais áudio
            self.should_accept_audio = False
            self.is_generating = True
            self.is_recording = False
            
            # Enviar activity_end conforme documentação
            await self.session.send_realtime_input(activity_end=types.ActivityEnd())
            logger.info("🛑 [MANUAL-STOP] Atividade de gravação finalizada, esperando resposta do Gemini")
            
        except Exception as e:
            # Log específico para keepalive timeout
            if "keepalive ping timeout" in str(e):
                logger.warning(f"⚠️ [KEEPALIVE-TIMEOUT] Conexão perdida durante stop_recording - keepalive timeout. Marcando sessão como desconectada.")
                self.is_connected = False
                self.should_accept_audio = False
                # Não propagar o erro se for timeout, apenas marcar como desconectado
                return
            else:
                logger.error(f"Erro ao parar gravação: {e}")
            raise
    
    async def receive_responses(
        self,
        text_callback: Optional[Callable[[str], None]] = None,
        audio_callback: Optional[Callable[[bytes], None]] = None,
        function_call_callback: Optional[Callable[[List[Any]], None]] = None
    ):
        """
        Recebe respostas da Live API
        
        Args:
            text_callback: Callback para texto recebido
            audio_callback: Callback para áudio recebido
            function_call_callback: Callback para chamadas de função
        """
        if not self.is_connected or not self.session:
            raise RuntimeError("Não conectado à Live API")
        
        try:
            logger.info("🎧 [GEMINI-LISTEN] Iniciando escuta de respostas do Gemini...")
            
            async for response in self.session.receive():
                logger.info(f"🔍 [GEMINI-RESPONSE] Received response type: {type(response)}, hasattr text: {hasattr(response, 'text')}, hasattr data: {hasattr(response, 'data')}, hasattr server_content: {hasattr(response, 'server_content')}")
                
                # Log all available attributes for debugging
                response_attrs = [attr for attr in dir(response) if not attr.startswith('_')]
                logger.info(f"🔍 [GEMINI-RESPONSE] Available attributes: {response_attrs}")
                
                # Log exact values for debugging
                if hasattr(response, 'text'):
                    logger.info(f"🔍 [GEMINI-RESPONSE] response.text = {response.text}")
                if hasattr(response, 'data'):
                    logger.info(f"🔍 [GEMINI-RESPONSE] response.data = {response.data} (length: {len(response.data) if response.data else 'None'})")
                if hasattr(response, 'server_content'):
                    logger.info(f"🔍 [GEMINI-RESPONSE] response.server_content = {response.server_content}")
                
                # Processar texto direto
                if hasattr(response, 'text') and response.text is not None and text_callback:
                    logger.info(f"📝 [GEMINI-TEXT] Processing direct text response: {response.text[:100]}...")
                    text_callback(response.text)
                
                # Processar áudio direto
                if hasattr(response, 'data') and response.data is not None and audio_callback:
                    logger.info(f"🎵 [GEMINI-AUDIO] Processing direct audio response: {len(response.data)} bytes")
                    audio_callback(response.data)
                
                # Processar chamadas de função
                if hasattr(response, 'tool_call') and response.tool_call and function_call_callback:
                    logger.info(f"🔧 [GEMINI-FUNCTION] Processing function call response")
                    function_call_callback(response.tool_call.function_calls)
                
                # Processar conteúdo do servidor
                if hasattr(response, 'server_content') and response.server_content:
                    server_content = response.server_content
                    logger.info(f"🔍 [GEMINI-SERVER] Processing server_content, hasattr interrupted: {hasattr(server_content, 'interrupted')}, hasattr generation_complete: {hasattr(server_content, 'generation_complete')}, hasattr model_turn: {hasattr(server_content, 'model_turn')}")
                    
                    # Log server_content attributes
                    server_attrs = [attr for attr in dir(server_content) if not attr.startswith('_')]
                    logger.info(f"🔍 [GEMINI-SERVER] server_content attributes: {server_attrs}")
                    
                    # Verificar se foi interrompido
                    if hasattr(server_content, 'interrupted') and server_content.interrupted:
                        logger.info("⚠️ [GEMINI-INTERRUPT] Geração interrompida pelo usuário")
                        self.is_generating = False
                        self.should_accept_audio = False  # Para no modo manual até próximo start_recording
                        self.is_recording = False
                        break
                    
                    # Verificar se a geração está completa
                    if hasattr(server_content, 'generation_complete') and server_content.generation_complete:
                        logger.info("✅ [GEMINI-COMPLETE] Geração completa")
                        self.is_generating = False
                        self.should_accept_audio = False  # Para no modo manual até próximo start_recording
                        self.is_recording = False
                        
                        # Notificar que a geração foi completada via callback
                        if hasattr(self, '_completion_callback') and self._completion_callback:
                            try:
                                self._completion_callback()
                            except Exception as e:
                                logger.error(f"Erro ao executar completion callback: {e}")
                        
                        break
                    
                    # Processar conteúdo do modelo
                    if hasattr(server_content, 'model_turn') and server_content.model_turn:
                        model_turn = server_content.model_turn
                        logger.info(f"🔍 [GEMINI-TURN] Processing model_turn, hasattr parts: {hasattr(model_turn, 'parts')}")
                        
                        # Log model_turn attributes
                        model_turn_attrs = [attr for attr in dir(model_turn) if not attr.startswith('_')]
                        logger.info(f"🔍 [GEMINI-TURN] model_turn attributes: {model_turn_attrs}")
                        
                        if hasattr(model_turn, 'parts') and model_turn.parts:
                            logger.info(f"🔍 [GEMINI-PARTS] Found {len(model_turn.parts)} parts")
                            for i, part in enumerate(model_turn.parts):
                                part_attrs = [attr for attr in dir(part) if not attr.startswith('_')]
                                logger.info(f"🔍 [GEMINI-PART-{i}] Part attributes: {part_attrs}")
                                
                                # Log specific values
                                if hasattr(part, 'text'):
                                    logger.info(f"🔍 [GEMINI-PART-{i}] part.text = {part.text}")
                                if hasattr(part, 'inline_data'):
                                    logger.info(f"🔍 [GEMINI-PART-{i}] part.inline_data = {part.inline_data}")
                                    if part.inline_data:
                                        inline_data_attrs = [attr for attr in dir(part.inline_data) if not attr.startswith('_')]
                                        logger.info(f"🔍 [GEMINI-PART-{i}] inline_data attributes: {inline_data_attrs}")
                                        if hasattr(part.inline_data, 'data'):
                                            logger.info(f"🔍 [GEMINI-PART-{i}] inline_data.data length: {len(part.inline_data.data) if part.inline_data.data else 'None'}")
                                        if hasattr(part.inline_data, 'bytes'):
                                            logger.info(f"🔍 [GEMINI-PART-{i}] inline_data.bytes length: {len(part.inline_data.bytes) if part.inline_data.bytes else 'None'}")
                                
                                # Texto
                                if hasattr(part, 'text') and part.text and text_callback:
                                    logger.info(f"📝 [GEMINI-PART-TEXT] Processing text from part {i}: {part.text[:100]}...")
                                    text_callback(part.text)
                                
                                # Dados inline (áudio)
                                if hasattr(part, 'inline_data') and part.inline_data and audio_callback:
                                    logger.info(f"🎵 [GEMINI-PART-AUDIO] Found inline_data in part {i}")
                                    if hasattr(part.inline_data, 'data'):
                                        logger.info(f"🎵 [GEMINI-PART-AUDIO] Processing audio data: {len(part.inline_data.data)} bytes")
                                        audio_callback(part.inline_data.data)
                                    elif hasattr(part.inline_data, 'bytes'):
                                        logger.info(f"🎵 [GEMINI-PART-AUDIO] Processing audio bytes: {len(part.inline_data.bytes)} bytes")
                                        audio_callback(part.inline_data.bytes)
                                    else:
                                        inline_data_attrs = [attr for attr in dir(part.inline_data) if not attr.startswith('_')]
                                        logger.warning(f"🎵 [GEMINI-PART-AUDIO] inline_data found but no data/bytes attributes. Available: {inline_data_attrs}")
                                else:
                                    if hasattr(part, 'inline_data'):
                                        logger.info(f"🔍 [GEMINI-PART-{i}] Has inline_data but no audio_callback or data is None")
                                    else:
                                        logger.info(f"🔍 [GEMINI-PART-{i}] No inline_data found")
                        else:
                            logger.info(f"🔍 [GEMINI-TURN] model_turn has no parts or parts is empty")
                    else:
                        logger.info(f"🔍 [GEMINI-SERVER] server_content has no model_turn or model_turn is None")
                else:
                    logger.info(f"🔍 [GEMINI-RESPONSE] No server_content found")
                
        except Exception as e:
            logger.error(f"Erro ao receber respostas: {e}")
            raise
    
    async def send_function_response(
        self,
        function_responses: List[Dict[str, Any]]
    ):
        """
        Envia resposta de uma chamada de função
        
        Args:
            function_responses: Lista de respostas de função
        """
        if not self.is_connected or not self.session:
            raise RuntimeError("Não conectado à Live API")
        
        try:
            # Converter para o formato correto
            responses = []
            for resp in function_responses:
                function_response = types.FunctionResponse(
                    id=resp.get("id"),
                    name=resp.get("name"),
                    response=resp.get("response", {})
                )
                responses.append(function_response)
            
            await self.session.send_tool_response(function_responses=responses)
            logger.info(f"Enviadas {len(responses)} respostas de função")
            
        except Exception as e:
            logger.error(f"Erro ao enviar resposta de função: {e}")
            raise
    
    async def disconnect(self):
        """
        Desconecta da Live API
        """
        if self.session and self.is_connected:
            try:
                # A sessão será fechada automaticamente quando sair do context manager
                self.is_connected = False
                self.session = None
                logger.info("Desconectado da Live API")
                
            except Exception as e:
                logger.error(f"Erro ao desconectar: {e}")
    
    def process_audio_for_live_api(self, audio_data: np.ndarray, sample_rate: int = 16000) -> bytes:
        """
        Processa dados de áudio para o formato correto da Live API
        
        Args:
            audio_data: Array numpy com dados de áudio
            sample_rate: Taxa de amostragem (deve ser 16000 para entrada)
            
        Returns:
            Dados de áudio em bytes (16-bit PCM, little-endian)
        """
        try:
            # Garantir que está em 16-bit PCM
            if audio_data.dtype != np.int16:
                # Normalizar e converter para int16
                audio_data = (audio_data * 32767).astype(np.int16)
            
            # Garantir que é mono
            if len(audio_data.shape) > 1:
                audio_data = np.mean(audio_data, axis=1).astype(np.int16)
            
            # Converter para bytes (little-endian)
            audio_bytes = audio_data.tobytes()
            
            logger.debug(f"Áudio processado: {len(audio_bytes)} bytes, taxa: {sample_rate}Hz")
            return audio_bytes
            
        except Exception as e:
            logger.error(f"Erro ao processar áudio: {e}")
            raise
    
    def process_audio_from_live_api(self, audio_bytes: bytes, sample_rate: int = 24000) -> np.ndarray:
        """
        Processa dados de áudio recebidos da Live API
        
        Args:
            audio_bytes: Dados de áudio em bytes da Live API
            sample_rate: Taxa de amostragem (24000 para saída da Live API)
            
        Returns:
            Array numpy com dados de áudio
        """
        try:
            # Converter bytes para array numpy (16-bit PCM, little-endian)
            audio_data = np.frombuffer(audio_bytes, dtype=np.int16)
            
            logger.debug(f"Áudio recebido: {len(audio_data)} samples, taxa: {sample_rate}Hz")
            return audio_data
            
        except Exception as e:
            logger.error(f"Erro ao processar áudio recebido: {e}")
            raise 