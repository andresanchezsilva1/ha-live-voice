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
    
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash-preview-native-audio-dialog"):
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
        
        logger.info(f"Cliente Live API inicializado - modelo: {model}")
    
    def set_function_declarations(self, function_declarations: List[Dict[str, Any]]):
        """
        Define as declarações de função para function calling
        
        Args:
            function_declarations: Lista de declarações de função
        """
        self.function_declarations = function_declarations
        logger.info(f"Configuradas {len(function_declarations)} declarações de função")
    
    async def connect_audio_session(
        self,
        system_instruction: Optional[str] = None,
        voice_name: str = "Kore",
        language_code: str = "pt-BR",
        enable_function_calling: bool = True
    ) -> Any:
        """
        Conecta à Live API com configuração para áudio
        
        Args:
            system_instruction: Instruções do sistema
            voice_name: Nome da voz (Puck, Charon, Kore, Fenrir, Aoede, Leda, Orus, Zephyr)
            language_code: Código do idioma (pt-BR para português brasileiro)
            enable_function_calling: Se deve habilitar function calling
            
        Returns:
            Context manager da sessão ativa da Live API
        """
        try:
            # Configuração da sessão
            config = {
                "response_modalities": ["AUDIO"],  # Volta para só áudio como estava funcionando
                "speech_config": {
                    "voice_config": {
                        "prebuilt_voice_config": {
                            "voice_name": voice_name
                        }
                    },
                    "language_code": language_code
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
        Envia dados de áudio em tempo real
        
        Args:
            audio_data: Dados de áudio em bytes (16-bit PCM, 16kHz, mono)
            mime_type: Tipo MIME do áudio
        """
        if not self.is_connected or not self.session:
            raise RuntimeError("Não conectado à Live API")
        
        try:
            await self.session.send_realtime_input(
                audio=types.Blob(data=audio_data, mime_type=mime_type)
            )
            logger.debug(f"Dados de áudio enviados: {len(audio_data)} bytes")
            
        except Exception as e:
            logger.error(f"Erro ao enviar dados de áudio: {e}")
            raise

    async def send_turn_complete(self):
        """
        Sinaliza ao Gemini que o turno do usuário terminou e ele deve responder
        Baseado na documentação oficial: https://ai.google.dev/api/live
        """
        if not self.is_connected or not self.session:
            raise RuntimeError("Não conectado à Live API")
        
        try:
            # Baseado na documentação oficial do Google Gemini Live API
            # Para sinalizar fim do turno após enviar áudio, usamos send_client_content
            # com turns vazio e turn_complete=True
            await self.session.send_client_content(
                turns=[],  # Lista vazia de turnos
                turn_complete=True  # Sinaliza fim do turno
            )
            logger.debug("Turn complete sinalizado ao Gemini usando send_client_content")
            
        except Exception as e:
            logger.error(f"Erro ao enviar turn complete: {e}")
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
            async for response in self.session.receive():
                logger.info(f"🔍 [GEMINI-RESPONSE] Received response type: {type(response)}, hasattr text: {hasattr(response, 'text')}, hasattr data: {hasattr(response, 'data')}, hasattr server_content: {hasattr(response, 'server_content')}")
                
                # Log all available attributes for debugging
                response_attrs = [attr for attr in dir(response) if not attr.startswith('_')]
                logger.debug(f"🔍 [GEMINI-RESPONSE] Available attributes: {response_attrs}")
                
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
                    
                    # Verificar se foi interrompido
                    if hasattr(server_content, 'interrupted') and server_content.interrupted:
                        logger.info("⚠️ [GEMINI-INTERRUPT] Geração interrompida pelo usuário")
                        break
                    
                    # Verificar se a geração está completa
                    if hasattr(server_content, 'generation_complete') and server_content.generation_complete:
                        logger.info("✅ [GEMINI-COMPLETE] Geração completa")
                        break
                    
                    # Processar conteúdo do modelo
                    if hasattr(server_content, 'model_turn') and server_content.model_turn:
                        model_turn = server_content.model_turn
                        logger.info(f"🔍 [GEMINI-TURN] Processing model_turn, hasattr parts: {hasattr(model_turn, 'parts')}")
                        
                        if hasattr(model_turn, 'parts') and model_turn.parts:
                            logger.info(f"🔍 [GEMINI-PARTS] Found {len(model_turn.parts)} parts")
                            for i, part in enumerate(model_turn.parts):
                                part_attrs = [attr for attr in dir(part) if not attr.startswith('_')]
                                logger.info(f"🔍 [GEMINI-PART-{i}] Part attributes: {part_attrs}")
                                
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