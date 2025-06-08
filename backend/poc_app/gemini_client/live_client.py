#!/usr/bin/env python3
"""
Cliente Gemini Live API - Implementação baseada na documentação oficial
https://ai.google.dev/gemini-api/docs/live?hl=pt-br
"""

import asyncio
import logging
import json
import time
from typing import AsyncGenerator, Optional, Dict, Any, List, Callable
from google import genai
from google.genai import types

from .ha_functions import HA_FUNCTION_DECLARATIONS

logger = logging.getLogger(__name__)


class GeminiLiveClient:
    """
    Cliente para Live API do Gemini - Streaming de áudio bidirecional em tempo real
    Baseado na documentação oficial: https://ai.google.dev/gemini-api/docs/live?hl=pt-br
    """
    
    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash-exp"):
        """
        Inicializa o cliente da Live API
        
        Args:
            api_key: Chave da API do Google AI
            model_name: Nome do modelo Live (gemini-2.0-flash-exp)
        """
        if not api_key:
            raise ValueError("API key é obrigatória")
        
        self.api_key = api_key
        self.model_name = model_name
        self.client = genai.Client(api_key=api_key)
        self.session = None
        self.is_connected = False
        
        # Configurações conforme documentação
        self._last_activity = time.time()
        self._session_timeout = 15 * 60  # 15 minutos conforme documentação
        self._session_id = None
        
        # Inicializar cliente conforme documentação
        try:
            logger.info(f"Cliente Gemini Live inicializado: {model_name}")
        except Exception as e:
            logger.error(f"Erro ao inicializar cliente: {e}")
            raise
    
    async def connect(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """Conecta à sessão Live API"""
        try:
            # Configuração padrão para áudio
            default_config = {
                "response_modalities": ["AUDIO"],
                "speech_config": {
                    "voice_config": {"prebuilt_voice_config": {"voice_name": "Aoede"}},
                    "language_code": "pt-BR"
                },
                "system_instruction": (
                    "Você é um assistente de casa inteligente que fala português brasileiro. "
                    "Responda de forma concisa e natural."
                )
                # Removendo tools temporariamente para testar conectividade
                # "tools": HA_FUNCTION_DECLARATIONS
            }
            
            # Se config personalizado for fornecido, usar ele completamente
            final_config = config if config else default_config
            
            # Usar context manager corretamente
            self._session_context = self.client.aio.live.connect(
                model=self.model_name,
                config=final_config
            )
            
            # Entrar no context manager
            self.session = await self._session_context.__aenter__()
            self.is_connected = True
            logger.info("Conectado à Gemini Live API")
            self._update_last_activity()
            return True
            
        except Exception as e:
            logger.error(f"Erro ao conectar à Live API: {e}")
            self.is_connected = False
            return False
    
    async def disconnect(self):
        """Desconecta da sessão Live API"""
        if hasattr(self, '_session_context') and self.is_connected:
            try:
                await self._session_context.__aexit__(None, None, None)
                self.is_connected = False
                self.session = None
                logger.info("Desconectado da Gemini Live API")
            except Exception as e:
                logger.error(f"Erro ao desconectar: {e}")
        elif self.session and self.is_connected:
            try:
                # Fallback se não tiver context manager
                await self.session.close()
                self.is_connected = False
                logger.info("Desconectado da Gemini Live API")
            except Exception as e:
                logger.error(f"Erro ao desconectar: {e}")
    
    async def send_text_input(self, text: str) -> bool:
        """Envia entrada de texto para a sessão - conforme documentação oficial"""
        if not self.session or not self.is_connected:
            logger.error("Sessão não conectada")
            return False
        
        try:
            # Usar o método correto da API conforme documentação
            await self.session.send_client_content(
                turns={"role": "user", "parts": [{"text": text}]}, 
                turn_complete=True
            )
            logger.debug(f"Texto enviado: {text}")
            self._update_last_activity()
            return True
            
        except Exception as e:
            logger.error(f"Erro ao enviar texto: {e}")
            return False
    
    async def send_audio_chunk(self, audio_data: bytes) -> bool:
        """Envia chunk de áudio para a sessão - conforme documentação oficial"""
        if not self.session or not self.is_connected:
            logger.error("Sessão não conectada")
            return False
        
        try:
            # Para áudio, usar send_realtime_input conforme documentação
            await self.session.send_realtime_input(
                audio=types.Blob(data=audio_data, mime_type="audio/pcm;rate=16000")
            )
            logger.debug(f"Chunk de áudio enviado: {len(audio_data)} bytes")
            self._update_last_activity()
            return True
            
        except Exception as e:
            logger.error(f"Erro ao enviar áudio: {e}")
            return False
    
    async def receive_responses(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Recebe respostas da sessão em tempo real"""
        if not self.session or not self.is_connected:
            logger.error("Sessão não conectada")
            return
        
        try:
            async for response in self.session.receive():
                if response:
                    # Processar diferentes tipos de resposta conforme documentação
                    processed = self._process_response(response)
                    if processed:
                        yield processed
                    
        except Exception as e:
            logger.error(f"Erro ao receber respostas: {e}")
    
    def _process_response(self, response) -> Optional[Dict[str, Any]]:
        """Processa resposta da API conforme documentação oficial"""
        try:
            result = {
                "type": "unknown",
                "data": None,
                "raw": str(response)
            }
            
            # Verificar se é resposta de texto
            if hasattr(response, 'text') and response.text is not None:
                result["type"] = "text"
                result["data"] = response.text
                logger.debug(f"Texto recebido: {response.text}")
                return result
            
            # Verificar se é resposta de áudio
            if hasattr(response, 'data') and response.data is not None:
                result["type"] = "audio"
                result["data"] = response.data
                logger.debug(f"Áudio recebido: {len(response.data)} bytes")
                return result
            
            # Verificar se há server_content
            if hasattr(response, 'server_content') and response.server_content:
                server_content = response.server_content
                
                # Verificar model_turn
                if hasattr(server_content, 'model_turn') and server_content.model_turn:
                    model_turn = server_content.model_turn
                    if hasattr(model_turn, 'parts') and model_turn.parts:
                        for part in model_turn.parts:
                            # Verificar inline_data (áudio)
                            if hasattr(part, 'inline_data') and part.inline_data:
                                result["type"] = "audio"
                                result["data"] = part.inline_data.data
                                logger.debug(f"Áudio inline recebido: {len(part.inline_data.data)} bytes")
                                return result
                            # Verificar texto
                            elif hasattr(part, 'text') and part.text:
                                result["type"] = "text"
                                result["data"] = part.text
                                logger.debug(f"Texto inline recebido: {part.text}")
                                return result
                
                # Verificar transcrições
                if hasattr(server_content, 'output_transcription') and server_content.output_transcription:
                    result["type"] = "transcription"
                    result["data"] = server_content.output_transcription.text
                    logger.debug(f"Transcrição recebida: {server_content.output_transcription.text}")
                    return result
            
            # Verificar tool_call
            if hasattr(response, 'tool_call') and response.tool_call:
                result["type"] = "function_call"
                result["data"] = {
                    "function_calls": []
                }
                for fc in response.tool_call.function_calls:
                    result["data"]["function_calls"].append({
                        "id": fc.id,
                        "name": fc.name,
                        "args": dict(fc.args) if hasattr(fc, 'args') else {}
                    })
                logger.debug(f"Function call recebida: {result['data']}")
                return result
            
            # Se chegou até aqui, log para debug
            logger.debug(f"Resposta não processada: {type(response)} - {dir(response)}")
            return None
            
        except Exception as e:
            logger.error(f"Erro ao processar resposta: {e}")
            return {"type": "error", "data": str(e), "raw": str(response)}
    
    async def process_voice_command(self, audio_data: bytes) -> AsyncGenerator[Dict[str, Any], None]:
        """Processa comando de voz e retorna respostas em tempo real"""
        if not self.is_connected:
            await self.connect()
        
        if not self.is_connected:
            yield {"type": "error", "data": "Não foi possível conectar à API"}
            return
        
        try:
            # Enviar áudio
            await self.send_audio_chunk(audio_data)
            
            # Receber respostas
            async for response in self.receive_responses():
                yield response
                
        except Exception as e:
            logger.error(f"Erro no processamento de voz: {e}")
            yield {"type": "error", "data": str(e)}
    
    async def start_conversation(self) -> bool:
        """Inicia uma nova conversa"""
        try:
            await self.connect()
            return self.is_connected
        except Exception as e:
            logger.error(f"Erro ao iniciar conversa: {e}")
            return False
    
    async def end_conversation(self):
        """Termina a conversa atual"""
        await self.disconnect()
    
    async def __aenter__(self):
        """Context manager entry"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        await self.disconnect()
    
    def _update_last_activity(self):
        """Atualiza timestamp da última atividade"""
        self._last_activity = time.time()
    
    def _is_session_expired(self) -> bool:
        """Verifica se a sessão expirou (15 min conforme documentação)"""
        if not self._last_activity:
            return False
        return (time.time() - self._last_activity) > self._session_timeout
    
    async def check_session_health(self) -> bool:
        """Verifica saúde da sessão"""
        if not self.is_connected or not self.session:
            return False
        if self._is_session_expired():
            logger.warning("⚠️ Sessão expirada por timeout")
            self.is_connected = False
            return False
        return True
    
    @property
    def session_id(self) -> Optional[str]:
        """Retorna ID da sessão atual"""
        return self._session_id


# Funções de conveniência para uso direto
async def create_live_audio_session(api_key: str, 
                                  function_declarations: Optional[List[Dict[str, Any]]] = None) -> GeminiLiveClient:
    """
    Cria e inicia uma sessão Live API configurada para áudio
    
    Args:
        api_key: Chave da API do Google AI
        function_declarations: Declarações de função opcionais
        
    Returns:
        Cliente Live API conectado e pronto para uso
    """
    client = GeminiLiveClient(api_key)
    await client.connect()
    return client


async def create_live_text_session(api_key: str,
                                 function_declarations: Optional[List[Dict[str, Any]]] = None) -> GeminiLiveClient:
    """
    Cria e inicia uma sessão Live API configurada para texto
    
    Args:
        api_key: Chave da API do Google AI  
        function_declarations: Declarações de função opcionais
        
    Returns:
        Cliente Live API conectado e pronto para uso
    """
    client = GeminiLiveClient(api_key)
    await client.connect()
    return client 