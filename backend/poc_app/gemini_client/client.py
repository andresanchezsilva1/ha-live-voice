import asyncio
import logging
from typing import Any, Dict, List, Optional, Union
from google import genai
from google.genai import types
import json
import time

logger = logging.getLogger(__name__)


class GeminiLiveClient:
    """
    Cliente para interagir com a API Gemini Live do Google para processamento de áudio em tempo real
    via WebSocket com streaming bidirecional de áudio e function calling para controle de Home Assistant
    """
    
    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash-live-001"):
        """
        Inicializa o cliente Gemini Live
        
        Args:
            api_key: Chave da API do Google AI
            model_name: Nome do modelo Gemini Live a ser usado
        """
        if not api_key:
            raise ValueError("API key é obrigatória")
            
        self.api_key = api_key
        self.model_name = model_name
        self._client = None
        self._session = None
        self._is_connected = False
        self._function_handler = None  # Handler para function calls
        
        # Configurações de gerenciamento de sessão
        self._max_reconnect_attempts = 3
        self._reconnect_delay = 1.0
        self._session_timeout = 300  # 5 minutos
        self._last_activity = None
        self._connection_errors = 0
        self._session_id = None
        
        # Configuração do cliente para Live API
        try:
            self._client = genai.Client(api_key=api_key)
            logger.info(f"Cliente Gemini Live inicializado com modelo: {model_name}")
        except Exception as e:
            logger.error(f"Erro ao inicializar cliente Gemini: {e}")
            raise
    
    def set_function_handler(self, function_handler):
        """
        Define o handler de função para processar function calls
        
        Args:
            function_handler: Instância de HomeAssistantFunctionHandler
        """
        self._function_handler = function_handler
        logger.info("Handler de função configurado")
    
    async def start_audio_session(self, function_declarations: Optional[List[Dict[str, Any]]] = None) -> Any:
        """
        Inicia uma nova sessão de streaming de áudio com a Live API via WebSocket
        
        Args:
            function_declarations: Lista de declarações de função para function calling
            
        Returns:
            Context manager da sessão WebSocket ativa
            
        Raises:
            RuntimeError: Se não conseguir iniciar a sessão
        """
        try:
            # Configuração para streaming de áudio com Live API
            config = {
                "response_modalities": ["AUDIO"],  # Resposta em áudio
                "speech_config": {
                    "voice_config": {
                        "prebuilt_voice_config": {
                            "voice_name": "Aoede"  # Voz em português brasileiro
                        }
                    }
                },
                "system_instruction": "Você é um assistente de casa inteligente em português brasileiro. Responda de forma natural e amigável. Quando controlar dispositivos, forneça confirmações claras em português.",
            }
            
            # Adicionar function declarations se fornecidas
            if function_declarations:
                config["tools"] = [{"function_declarations": function_declarations}]
            
            # Estabelecer conexão WebSocket com Live API
            # A API retorna um async context manager
            self._session_context = self._client.aio.live.connect(
                model=self.model_name,
                config=config
            )
            
            # Entrar no context manager para obter a sessão
            self._session = await self._session_context.__aenter__()
            
            self._is_connected = True
            self._update_last_activity()
            self._session_id = f"gemini_live_{int(time.time())}"
            
            logger.info(f"Sessão Live API iniciada com sucesso: {self._session_id}")
            logger.info("Streaming de áudio bidirecional ativo via WebSocket")
            return self._session
            
        except Exception as e:
            logger.error(f"Erro ao iniciar sessão Live API: {e}")
            self._is_connected = False
            raise RuntimeError(f"Falha ao iniciar sessão Gemini Live: {e}")
    
    async def send_audio_stream(self, audio_chunk: bytes, mime_type: str = "audio/pcm;rate=16000") -> None:
        """
        Envia chunk de áudio para o streaming em tempo real
        
        Args:
            audio_chunk: Dados do áudio em bytes (16-bit PCM, 16kHz, mono)
            mime_type: Tipo MIME do áudio conforme documentação Live API
        """
        if not self._session or not self._is_connected:
            raise RuntimeError("Sessão Live API não iniciada")
        
        if not audio_chunk:
            logger.warning("Chunk de áudio vazio recebido")
            return
            
        try:
            # Enviar áudio em tempo real via WebSocket
            # Usando o formato correto para a nova API Gemini Live
            message = types.LiveClientRealtimeInput(
                media_chunks=[
                    types.LiveClientRealtimeInput.MediaChunk(
                        data=audio_chunk,
                        mime_type=mime_type
                    )
                ]
            )
            
            await self._session.send(message)
            
            self._update_last_activity()
            logger.debug(f"Chunk de áudio enviado ({len(audio_chunk)} bytes)")
            
        except Exception as e:
            logger.error(f"Erro ao enviar chunk de áudio: {e}")
            await self._handle_connection_error()
    
    async def send_text_message(self, message: str) -> None:
        """
        Envia mensagem de texto para a sessão Live API
        
        Args:
            message: Mensagem de texto para enviar
        """
        if not self._session or not self._is_connected:
            raise RuntimeError("Sessão Live API não iniciada")
            
        try:
            logger.debug(f"Enviando mensagem de texto: {message}")
            
            # Usando o formato correto para a nova API Gemini Live
            client_content = types.LiveClientContent(
                turns=[
                    types.Turn(
                        role="user",
                        parts=[types.Part(text=message)]
                    )
                ],
                turn_complete=True
            )
            
            await self._session.send(client_content)
            
            self._update_last_activity()
            
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem de texto: {e}")
            await self._handle_connection_error()

    async def receive_audio_responses(self):
        """
        Escuta e processa respostas de áudio em tempo real da Live API
        
        Yields:
            Dicionários com dados de áudio e transcrições conforme chegam
        """
        if not self._session or not self._is_connected:
            raise RuntimeError("Sessão Live API não iniciada")
        
        try:
            async for message in self._session:
                response_data = await self._process_live_response(message)
                if response_data:
                    yield response_data
                    
        except Exception as e:
            logger.error(f"Erro ao receber respostas de áudio: {e}")
            await self._handle_connection_error()

    async def _process_live_response(self, message: Any) -> Optional[Dict[str, Any]]:
        """
        Processa resposta da Live API em tempo real
        
        Args:
            message: Mensagem recebida da Live API
            
        Returns:
            Dicionário estruturado com dados da resposta
        """
        try:
            result = {
                "audio_data": None,
                "input_transcription": None,
                "output_transcription": None,
                "function_calls": [],
                "text": None,
                "session_complete": False,
                "interrupted": False
            }
            
            # Processar dados de áudio
            if message.data:
                result["audio_data"] = message.data
                logger.debug("Dados de áudio recebidos")
            
            # Processar conteúdo do servidor
            if message.server_content:
                # Transcrição de entrada
                if message.server_content.input_transcription:
                    result["input_transcription"] = message.server_content.input_transcription.text
                    logger.debug(f"Transcrição entrada: {result['input_transcription']}")
                
                # Transcrição de saída
                if message.server_content.output_transcription:
                    result["output_transcription"] = message.server_content.output_transcription.text
                    logger.debug(f"Transcrição saída: {result['output_transcription']}")
                
                # Turn completo
                if message.server_content.turn_complete:
                    result["session_complete"] = True
                
                # Interrupção
                if message.server_content.interrupted:
                    result["interrupted"] = True
                    logger.info("Geração interrompida pelo usuário")
                
                # Conteúdo do modelo
                if message.server_content.model_turn:
                    for part in message.server_content.model_turn.parts:
                        if part.inline_data:
                            result["audio_data"] = part.inline_data.data
                        elif part.text:
                            result["text"] = part.text
            
            # Processar function calls
            if hasattr(message, 'tool_call') and message.tool_call:
                for function_call in message.tool_call.function_calls:
                    result["function_calls"].append({
                        "id": function_call.id,
                        "name": function_call.name,
                        "args": function_call.args if hasattr(function_call, 'args') else {}
                    })
                
                # Processar function calls se handler estiver configurado
                if self._function_handler and result["function_calls"]:
                    await self._handle_function_calls(result["function_calls"])
            
            return result if any([
                result["audio_data"],
                result["input_transcription"],
                result["output_transcription"],
                result["function_calls"],
                result["text"]
            ]) else None
            
        except Exception as e:
            logger.error(f"Erro ao processar resposta Live API: {e}")
            return None

    async def _handle_function_calls(self, function_calls: List[Dict[str, Any]]) -> None:
        """
        Processa function calls da Live API
        
        Args:
            function_calls: Lista de function calls para processar
        """
        if not self._function_handler:
            logger.warning("Handler de função não configurado para processar calls")
            return
        
        function_responses = []
        
        for call in function_calls:
            try:
                # Executar function call
                result = await self._function_handler.handle_function_call(
                    call["name"],
                    call["args"]
                )
                
                # Criar response conforme formato Live API
                function_response = types.FunctionResponse(
                    id=call["id"],
                    name=call["name"],
                    response={"result": result}
                )
                function_responses.append(function_response)
                
                logger.info(f"Function call {call['name']} executada: {result}")
                
            except Exception as e:
                logger.error(f"Erro ao executar function call {call['name']}: {e}")
                # Enviar erro como response
                error_response = types.FunctionResponse(
                    id=call["id"],
                    name=call["name"],
                    response={"error": str(e)}
                )
                function_responses.append(error_response)
        
        # Enviar responses de volta para Live API
        if function_responses:
            try:
                await self._session.send_tool_response(function_responses=function_responses)
                logger.debug(f"Enviadas {len(function_responses)} function responses")
            except Exception as e:
                logger.error(f"Erro ao enviar function responses: {e}")

    async def _handle_connection_error(self) -> None:
        """
        Trata erros de conexão da Live API
        """
        self._connection_errors += 1
        self._is_connected = False
        
        if self._connection_errors < self._max_reconnect_attempts:
            logger.warning(f"Erro de conexão {self._connection_errors}/{self._max_reconnect_attempts}. Tentando reconectar...")
            await asyncio.sleep(self._reconnect_delay)
            # Tentativa de reconexão seria implementada aqui
        else:
            logger.error("Número máximo de tentativas de reconexão atingido")

    async def process_audio_chunk(self, audio_chunk: bytes, mime_type: str = "audio/pcm;rate=16000") -> Optional[Dict[str, Any]]:
        """
        MÉTODO LEGADO: Mantido para compatibilidade
        Usar send_audio_stream() e receive_audio_responses() para streaming real
        """
        logger.warning("Método legado. Use send_audio_stream() e receive_audio_responses() para Live API")
        await self.send_audio_stream(audio_chunk, mime_type)
        return None

    async def process_text_message(self, message: str) -> Optional[Dict[str, Any]]:
        """
        MÉTODO LEGADO: Mantido para compatibilidade
        Usar send_text_message() para Live API
        """
        logger.warning("Método legado. Use send_text_message() para Live API")
        await self.send_text_message(message)
        return None

    async def get_audio_response(self, function_result: Dict[str, Any], context_message: str = None) -> Optional[Dict[str, Any]]:
        """
        Gera resposta em áudio para resultado de função usando Live API
        
        Args:
            function_result: Resultado da função executada
            context_message: Mensagem de contexto opcional
            
        Returns:
            Dicionário com resposta de áudio ou None se erro
        """
        if not self._session or not self._is_connected:
            logger.warning("Sessão não disponível para resposta de áudio")
            return None
            
        try:
            # Gerar mensagem contextual baseada no resultado
            if not context_message:
                context_message = self._generate_context_message(function_result)
            
            # Enviar mensagem para gerar resposta de áudio
            await self.send_text_message(context_message)
            
            # A resposta virá através do stream receive_audio_responses()
            logger.info(f"Solicitada resposta de áudio para: {context_message[:50]}...")
            return {"status": "requested", "context": context_message}
            
        except Exception as e:
            logger.error(f"Erro ao solicitar resposta de áudio: {e}")
            return None

    def _generate_context_message(self, function_result: Dict[str, Any]) -> str:
        """
        Gera mensagem contextual em português para resultado de função
        
        Args:
            function_result: Resultado da execução da função
            
        Returns:
            Mensagem em português para o usuário
        """
        try:
            if function_result.get("success"):
                action = function_result.get("action", "ação")
                device = function_result.get("device", "dispositivo")
                
                # Mapear ações para português
                action_map = {
                    "turn_on": "ligou",
                    "turn_off": "desligou", 
                    "set_brightness": "ajustou o brilho",
                    "set_temperature": "ajustou a temperatura",
                    "activate": "ativou",
                    "deactivate": "desativou"
                }
                
                action_pt = action_map.get(action, action)
                
                messages = [
                    f"Perfeito! {action_pt.capitalize()} o {device} com sucesso.",
                    f"Pronto! O {device} foi {action_pt}.",
                    f"Feito! {device} {action_pt} conforme solicitado."
                ]
                
                import random
                return random.choice(messages)
            else:
                error = function_result.get("error", "erro desconhecido")
                return f"Desculpe, não consegui completar a ação. Erro: {error}"
                
        except Exception as e:
            logger.error(f"Erro ao gerar mensagem contextual: {e}")
            return "Ação processada, mas não consegui gerar confirmação."

    async def process_with_audio_response(self, input_data: Union[str, bytes], mime_type: str = "audio/pcm;rate=16000") -> Dict[str, Any]:
        """
        Processa entrada (texto ou áudio) e retorna resposta com áudio usando Live API
        
        Args:
            input_data: Dados de entrada (string para texto, bytes para áudio)
            mime_type: Tipo MIME para dados de áudio
            
        Returns:
            Dicionário com resposta completa incluindo áudio
        """
        if not self._session or not self._is_connected:
            return {"error": "Sessão Live API não disponível", "audio": None}
        
        try:
            # Enviar dados conforme tipo
            if isinstance(input_data, str):
                await self.send_text_message(input_data)
                logger.info(f"Texto enviado para Live API: {input_data[:50]}...")
            else:
                await self.send_audio_stream(input_data, mime_type)
                logger.info(f"Áudio enviado para Live API ({len(input_data)} bytes)")
            
            # Coletar primeira resposta de áudio
            audio_chunks = []
            transcriptions = []
            
            async for response in self.receive_audio_responses():
                if response.get("audio_data"):
                    audio_chunks.append(response["audio_data"])
                
                if response.get("output_transcription"):
                    transcriptions.append(response["output_transcription"])
                
                # Parar ao completar turn
                if response.get("session_complete"):
                    break
            
            # Combinar chunks de áudio
            combined_audio = b''.join(audio_chunks) if audio_chunks else None
            combined_text = ' '.join(transcriptions) if transcriptions else None
            
            result = {
                "audio": combined_audio,
                "text": combined_text,
                "success": combined_audio is not None,
                "input_type": "text" if isinstance(input_data, str) else "audio"
            }
            
            logger.info(f"Resposta Live API processada: áudio={len(combined_audio) if combined_audio else 0} bytes, texto='{combined_text}'")
            return result
            
        except Exception as e:
            logger.error(f"Erro ao processar com resposta de áudio: {e}")
            return {"error": str(e), "audio": None}

    async def send_function_result(self, function_name: str, result: Any) -> Optional[Dict[str, Any]]:
        """
        Envia resultado de função e gera resposta em áudio contextual
        
        Args:
            function_name: Nome da função executada
            result: Resultado da função
            
        Returns:
            Dicionário com resposta de áudio gerada
        """
        if not self._session or not self._is_connected:
            logger.warning("Sessão não disponível para envio de resultado")
            return None
            
        try:
            # Preparar resultado estruturado
            function_result = {
                "function": function_name,
                "success": result.get("success", True) if isinstance(result, dict) else True,
                "data": result,
                "action": result.get("action") if isinstance(result, dict) else "executada",
                "device": result.get("device") if isinstance(result, dict) else "dispositivo"
            }
            
            # Gerar e enviar resposta de áudio
            audio_response = await self.get_audio_response(function_result)
            
            logger.info(f"Resultado de {function_name} enviado para resposta de áudio")
            return audio_response
            
        except Exception as e:
            logger.error(f"Erro ao enviar resultado de função: {e}")
            return None

    async def close_session(self):
        """
        Fecha a sessão Live API WebSocket
        """
        try:
            if self._session and self._is_connected and hasattr(self, '_session_context'):
                # Sair do context manager adequadamente
                await self._session_context.__aexit__(None, None, None)
                logger.info("Sessão Live API fechada")
        except Exception as e:
            logger.error(f"Erro ao fechar sessão: {e}")
        finally:
            self._session = None
            self._session_context = None
            self._is_connected = False

    @property
    def is_connected(self) -> bool:
        """Retorna True se a sessão Live API estiver ativa"""
        return self._is_connected and self._session is not None

    @property
    def has_function_handler(self) -> bool:
        """Retorna True se um handler de função estiver configurado"""
        return self._function_handler is not None

    def _update_last_activity(self):
        """Atualiza timestamp da última atividade"""
        self._last_activity = time.time()

    def _is_session_expired(self) -> bool:
        """Verifica se a sessão expirou baseado no timeout"""
        if not self._last_activity:
            return False
        return (time.time() - self._last_activity) > self._session_timeout

    async def check_session_health(self) -> bool:
        """
        Verifica saúde da sessão Live API
        
        Returns:
            True se a sessão estiver saudável
        """
        try:
            if not self._is_connected or not self._session:
                logger.warning("Sessão não conectada")
                return False
            
            if self._is_session_expired():
                logger.warning("Sessão expirada por timeout")
                self._is_connected = False
                return False
            
            # Na Live API WebSocket, podemos verificar se ainda está conectada
            # tentando uma operação simples
            return True
            
        except Exception as e:
            logger.error(f"Erro ao verificar saúde da sessão: {e}")
            self._is_connected = False
            return False

    async def ensure_connected(self, function_declarations: Optional[List[Dict[str, Any]]] = None) -> bool:
        """
        Garante que há uma conexão Live API ativa
        
        Args:
            function_declarations: Declarações de função para nova sessão
            
        Returns:
            True se conexão estiver ativa
        """
        if await self.check_session_health():
            return True
        
        logger.info("Reconectando sessão Live API...")
        return await self.reconnect_with_retry(function_declarations)

    async def reconnect_with_retry(self, function_declarations: Optional[List[Dict[str, Any]]] = None) -> bool:
        """
        Tenta reconectar com retry usando Live API
        
        Args:
            function_declarations: Declarações de função para nova sessão
            
        Returns:
            True se reconexão for bem-sucedida
        """
        for attempt in range(self._max_reconnect_attempts):
            try:
                logger.info(f"Tentativa de reconexão {attempt + 1}/{self._max_reconnect_attempts}")
                
                if await self.reconnect(function_declarations):
                    logger.info("Reconexão Live API bem-sucedida")
                    self._connection_errors = 0
                    return True
                
            except Exception as e:
                logger.error(f"Falha na tentativa {attempt + 1}: {e}")
            
            if attempt < self._max_reconnect_attempts - 1:
                delay = self._reconnect_delay * (2 ** attempt)  # Backoff exponencial
                logger.info(f"Aguardando {delay}s antes da próxima tentativa...")
                await asyncio.sleep(delay)
        
        logger.error("Todas as tentativas de reconexão falharam")
        return False

    async def reconnect(self, function_declarations: Optional[List[Dict[str, Any]]] = None) -> bool:
        """
        Reconecta a sessão Live API
        
        Args:
            function_declarations: Declarações de função para nova sessão
            
        Returns:
            True se reconexão for bem-sucedida
        """
        try:
            # Fechar sessão atual se existir
            await self.close_session()
            
            # Aguardar um pouco antes de reconectar
            await asyncio.sleep(1)
            
            # Iniciar nova sessão
            await self.start_audio_session(function_declarations)
            
            return self._is_connected
            
        except Exception as e:
            logger.error(f"Erro na reconexão: {e}")
            return False 