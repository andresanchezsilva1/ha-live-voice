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
    e function calling para controle de Home Assistant
    """
    
    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash-exp"):
        """
        Inicializa o cliente Gemini Live
        
        Args:
            api_key: Chave da API do Google AI
            model_name: Nome do modelo Gemini a ser usado
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
        
        # Configuração do cliente
        try:
            genai.configure(api_key=api_key)
            self._client = genai.GenerativeModel(
                model_name=model_name,
                generation_config=types.GenerationConfig(
                    temperature=0.2,
                    max_output_tokens=1024,
                    response_modalities=["AUDIO", "TEXT"]
                )
            )
            logger.info(f"Cliente Gemini inicializado com modelo: {model_name}")
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
        Inicia uma nova sessão de streaming de áudio com function calling
        
        Args:
            function_declarations: Lista de declarações de função para function calling
            
        Returns:
            Sessão de chat ativa
            
        Raises:
            RuntimeError: Se não conseguir iniciar a sessão
        """
        try:
            # Configurar ferramentas se fornecidas
            tools = None
            if function_declarations:
                tools = [types.Tool(function_declarations=function_declarations)]
                logger.info(f"Configuradas {len(function_declarations)} funções para function calling")
            
            # Iniciar chat com configuração
            self._session = self._client.start_chat(
                tools=tools,
                enable_automatic_function_calling=False  # Processaremos manualmente
            )
            
            self._is_connected = True
            logger.info("Sessão de áudio Gemini iniciada com sucesso")
            return self._session
            
        except Exception as e:
            logger.error(f"Erro ao iniciar sessão de áudio: {e}")
            self._is_connected = False
            raise RuntimeError(f"Falha ao iniciar sessão Gemini: {e}")
    
    async def process_audio_chunk(self, audio_chunk: bytes, mime_type: str = "audio/pcm") -> Optional[Dict[str, Any]]:
        """
        Processa um chunk de áudio e retorna a resposta
        
        Args:
            audio_chunk: Dados do áudio em bytes
            mime_type: Tipo MIME do áudio
            
        Returns:
            Dicionário com resposta processada ou None se erro
            
        Raises:
            RuntimeError: Se a sessão não estiver ativa
        """
        if not self._session or not self._is_connected:
            raise RuntimeError("Sessão não iniciada. Chame start_audio_session() primeiro")
        
        if not audio_chunk:
            logger.warning("Chunk de áudio vazio recebido")
            return None
            
        try:
            # Criar objeto de áudio
            audio_data = types.Part.from_bytes(
                data=audio_chunk,
                mime_type=mime_type
            )
            
            # Enviar áudio para processamento
            logger.debug(f"Enviando chunk de áudio ({len(audio_chunk)} bytes)")
            response = await self._session.send_message_async([audio_data])
            
            # Processar resposta
            processed_response = await self._process_response(response)
            logger.debug(f"Resposta processada: {processed_response}")
            
            return processed_response
            
        except Exception as e:
            logger.error(f"Erro ao processar chunk de áudio: {e}")
            return None
    
    async def process_text_message(self, message: str) -> Optional[Dict[str, Any]]:
        """
        Processa uma mensagem de texto
        
        Args:
            message: Mensagem de texto para processar
            
        Returns:
            Dicionário com resposta processada
        """
        if not self._session or not self._is_connected:
            raise RuntimeError("Sessão não iniciada. Chame start_audio_session() primeiro")
            
        try:
            logger.debug(f"Enviando mensagem de texto: {message}")
            response = await self._session.send_message_async(message)
            processed_response = await self._process_response(response)
            
            return processed_response
            
        except Exception as e:
            logger.error(f"Erro ao processar mensagem de texto: {e}")
            return None
    
    async def _process_response(self, response: Any) -> Dict[str, Any]:
        """
        Processa a resposta do Gemini e extrai informações relevantes
        
        Args:
            response: Resposta bruta do Gemini
            
        Returns:
            Dicionário estruturado com dados da resposta
        """
        try:
            result = {
                "text": None,
                "audio": None,
                "function_calls": [],
                "has_content": False
            }
            
            if response.candidates:
                candidate = response.candidates[0]
                
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        # Texto
                        if hasattr(part, 'text') and part.text:
                            result["text"] = part.text
                            result["has_content"] = True
                            logger.debug(f"Texto extraído: {part.text[:100]}...")
                        
                        # Áudio
                        if hasattr(part, 'inline_data') and part.inline_data:
                            result["audio"] = part.inline_data.data
                            result["has_content"] = True
                            logger.debug(f"Áudio extraído: {len(part.inline_data.data)} bytes")
                        
                        # Function calls
                        if hasattr(part, 'function_call') and part.function_call:
                            function_call = {
                                "name": part.function_call.name,
                                "args": dict(part.function_call.args)
                            }
                            result["function_calls"].append(function_call)
                            result["has_content"] = True
                            logger.info(f"Function call detectado: {function_call['name']}")
            
            return result
            
        except Exception as e:
            logger.error(f"Erro ao processar resposta: {e}")
            return {
                "text": None,
                "audio": None,
                "function_calls": [],
                "has_content": False,
                "error": str(e)
            }
    
    async def process_function_calls(self, function_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Processa uma lista de function calls usando o handler configurado
        
        Args:
            function_calls: Lista de function calls a processar
            
        Returns:
            Lista com resultados das execuções
        """
        if not self._function_handler:
            logger.warning("Handler de função não configurado. Function calls não serão processados.")
            return []
        
        results = []
        
        for function_call in function_calls:
            try:
                # Executar função via handler
                result = await self._function_handler.handle_function_call(function_call)
                results.append(result)
                
                # Enviar resultado de volta ao Gemini para continuar a conversa
                if result.get("success"):
                    await self.send_function_result(function_call["name"], result)
                
            except Exception as e:
                logger.error(f"Erro ao processar function call {function_call['name']}: {e}")
                error_result = {
                    "success": False,
                    "function_name": function_call["name"],
                    "error": str(e)
                }
                results.append(error_result)
        
        return results
    
    async def get_audio_response(self, function_result: Dict[str, Any], context_message: str = None) -> Optional[Dict[str, Any]]:
        """
        Gera uma resposta de áudio após a execução de uma função
        
        Args:
            function_result: Resultado da execução da função
            context_message: Mensagem de contexto opcional para guiar a resposta
            
        Returns:
            Dicionário com resposta de áudio ou None se erro
        """
        if not self._session or not self._is_connected:
            raise RuntimeError("Sessão não iniciada")
        
        try:
            # Preparar mensagem de contexto baseada no resultado da função
            if context_message is None:
                context_message = self._generate_context_message(function_result)
            
            logger.debug(f"Gerando resposta de áudio para: {context_message}")
            
            # Enviar mensagem para gerar resposta de áudio
            response = await self._session.send_message_async(context_message)
            
            # Processar resposta focando no áudio
            processed_response = await self._process_response(response)
            
            if processed_response.get("audio"):
                logger.info(f"Resposta de áudio gerada: {len(processed_response['audio'])} bytes")
            else:
                logger.warning("Nenhuma resposta de áudio foi gerada")
            
            return processed_response
            
        except Exception as e:
            logger.error(f"Erro ao gerar resposta de áudio: {e}")
            return None
    
    def _generate_context_message(self, function_result: Dict[str, Any]) -> str:
        """
        Gera uma mensagem de contexto baseada no resultado da função executada
        
        Args:
            function_result: Resultado da execução da função
            
        Returns:
            Mensagem de contexto para o Gemini
        """
        if not function_result.get("success"):
            return f"Houve um erro ao executar a função: {function_result.get('error', 'Erro desconhecido')}. Por favor, informe o usuário sobre o problema."
        
        function_name = function_result.get("function_name", "função")
        entity_id = function_result.get("result", {}).get("entity_id", "dispositivo")
        action = function_result.get("result", {}).get("action", "ação")
        
        # Gerar mensagem contextual baseada no tipo de função
        if "light" in function_name:
            if action == "turn_on":
                return f"A luz {entity_id} foi ligada com sucesso. Confirme para o usuário que a luz está agora acesa."
            elif action == "turn_off":
                return f"A luz {entity_id} foi desligada com sucesso. Confirme para o usuário que a luz está agora apagada."
            elif action == "toggle":
                return f"O estado da luz {entity_id} foi alternado com sucesso."
        
        elif "switch" in function_name:
            if action == "turn_on":
                return f"O interruptor {entity_id} foi ligado com sucesso."
            elif action == "turn_off":
                return f"O interruptor {entity_id} foi desligado com sucesso."
            elif action == "toggle":
                return f"O estado do interruptor {entity_id} foi alternado com sucesso."
        
        elif "scene" in function_name:
            return f"A cena {entity_id} foi ativada com sucesso. O ambiente está agora configurado conforme solicitado."
        
        elif "climate" in function_name:
            if action == "set_temperature":
                temp = function_result.get("result", {}).get("details", {}).get("temperature", "temperatura desejada")
                return f"A temperatura do {entity_id} foi ajustada para {temp}°C com sucesso."
            elif action == "set_hvac_mode":
                mode = function_result.get("result", {}).get("details", {}).get("hvac_mode", "modo solicitado")
                return f"O modo do {entity_id} foi alterado para {mode} com sucesso."
            else:
                return f"O sistema de clima {entity_id} foi {action} com sucesso."
        
        elif "media" in function_name:
            if action == "play":
                return f"A reprodução foi iniciada no {entity_id}."
            elif action == "pause":
                return f"A reprodução foi pausada no {entity_id}."
            elif action == "stop":
                return f"A reprodução foi interrompida no {entity_id}."
            elif action == "volume_set":
                volume = function_result.get("result", {}).get("details", {}).get("volume_level", "nível solicitado")
                return f"O volume do {entity_id} foi ajustado para {volume}."
            else:
                return f"Comando {action} executado com sucesso no {entity_id}."
        
        elif "sensor" in function_name or "get_entity_state" in function_name:
            state = function_result.get("result", {}).get("state", "estado atual")
            return f"O estado atual do {entity_id} é: {state}."
        
        elif "list_entities" in function_name:
            entities_count = len(function_result.get("result", {}).get("entities", []))
            domain = function_result.get("result", {}).get("domain", "tipo")
            return f"Encontrei {entities_count} dispositivos do tipo {domain} disponíveis."
        
        elif "cover" in function_name:
            if action == "open_cover":
                return f"A cobertura {entity_id} foi aberta com sucesso."
            elif action == "close_cover":
                return f"A cobertura {entity_id} foi fechada com sucesso."
            elif action == "set_cover_position":
                position = function_result.get("result", {}).get("details", {}).get("position", "posição solicitada")
                return f"A posição da cobertura {entity_id} foi ajustada para {position}%."
            else:
                return f"Comando {action} executado com sucesso na cobertura {entity_id}."
        
        elif "lock" in function_name:
            if action == "lock":
                return f"A fechadura {entity_id} foi travada com sucesso."
            elif action == "unlock":
                return f"A fechadura {entity_id} foi destravada com sucesso."
        
        # Mensagem genérica para casos não cobertos
        return f"A função {function_name} foi executada com sucesso no dispositivo {entity_id}."
    
    async def process_with_audio_response(self, input_data: Union[str, bytes], mime_type: str = "audio/pcm") -> Dict[str, Any]:
        """
        Processa entrada (áudio ou texto) com function calling e geração automática de resposta de áudio
        
        Args:
            input_data: Dados de entrada (texto ou áudio)
            mime_type: Tipo MIME se for áudio
            
        Returns:
            Resposta completa incluindo resultados de function calls e áudio de resposta
        """
        try:
            # Processar entrada inicial
            if isinstance(input_data, str):
                response = await self.process_text_message(input_data)
            elif isinstance(input_data, bytes):
                response = await self.process_audio_chunk(input_data, mime_type)
            else:
                raise ValueError("Tipo de entrada não suportado. Use str para texto ou bytes para áudio.")
            
            if not response:
                return {"error": "Falha ao processar entrada"}
            
            # Se houve function calls, processá-los e gerar resposta de áudio
            if response.get("function_calls") and self._function_handler:
                logger.info(f"Processando {len(response['function_calls'])} function calls")
                
                # Processar function calls
                function_results = await self.process_function_calls(response["function_calls"])
                response["function_results"] = function_results
                
                # Gerar resposta de áudio baseada nos resultados
                if function_results:
                    # Usar o primeiro resultado bem-sucedido para gerar resposta
                    successful_result = next((r for r in function_results if r.get("success")), None)
                    
                    if successful_result:
                        audio_response = await self.get_audio_response(successful_result)
                        if audio_response:
                            response["confirmation_audio"] = audio_response.get("audio")
                            response["confirmation_text"] = audio_response.get("text")
                            logger.info("Resposta de áudio de confirmação gerada")
                    else:
                        # Se todas as funções falharam, gerar resposta de erro
                        error_result = function_results[0] if function_results else {"error": "Função falhou"}
                        audio_response = await self.get_audio_response(error_result)
                        if audio_response:
                            response["error_audio"] = audio_response.get("audio")
                            response["error_text"] = audio_response.get("text")
            
            return response
            
        except Exception as e:
            logger.error(f"Erro no processamento com resposta de áudio: {e}")
            return {"error": str(e)}
    
    async def send_function_result(self, function_name: str, result: Any) -> Optional[Dict[str, Any]]:
        """
        Envia o resultado de uma function call de volta para o Gemini
        
        Args:
            function_name: Nome da função executada
            result: Resultado da execução da função
            
        Returns:
            Resposta do Gemini após receber o resultado
        """
        if not self._session or not self._is_connected:
            raise RuntimeError("Sessão não iniciada")
            
        try:
            # Criar resposta da função
            function_response = types.Part.from_function_response(
                name=function_name,
                response={"result": result}
            )
            
            logger.debug(f"Enviando resultado da função {function_name}: {result}")
            response = await self._session.send_message_async([function_response])
            
            return await self._process_response(response)
            
        except Exception as e:
            logger.error(f"Erro ao enviar resultado da função: {e}")
            return None
    
    async def close_session(self):
        """
        Fecha a sessão ativa e limpa recursos
        """
        try:
            if self._session:
                # Gemini não tem método explícito de close, apenas limpar referência
                self._session = None
                logger.info("Sessão Gemini fechada")
            
            self._is_connected = False
            
        except Exception as e:
            logger.error(f"Erro ao fechar sessão: {e}")
    
    @property
    def is_connected(self) -> bool:
        """Retorna se a sessão está ativa"""
        return self._is_connected
    
    @property
    def has_function_handler(self) -> bool:
        """Retorna se um handler de função está configurado"""
        return self._function_handler is not None
    
    def _update_last_activity(self):
        """Atualiza o timestamp da última atividade"""
        self._last_activity = time.time()
    
    def _is_session_expired(self) -> bool:
        """Verifica se a sessão expirou por inatividade"""
        if not self._last_activity:
            return False
        
        return (time.time() - self._last_activity) > self._session_timeout
    
    async def check_session_health(self) -> bool:
        """
        Verifica a saúde da sessão atual
        
        Returns:
            True se a sessão está saudável, False caso contrário
        """
        if not self._is_connected or not self._session:
            return False
        
        if self._is_session_expired():
            logger.warning("Sessão expirou por inatividade")
            return False
        
        try:
            # Tentar uma operação simples para verificar conectividade
            test_response = await self.process_text_message("ping")
            return test_response is not None
        except Exception as e:
            logger.warning(f"Verificação de saúde da sessão falhou: {e}")
            return False
    
    async def ensure_connected(self, function_declarations: Optional[List[Dict[str, Any]]] = None) -> bool:
        """
        Garante que a sessão está conectada, reconectando se necessário
        
        Args:
            function_declarations: Declarações de função para reconexão
            
        Returns:
            True se conectado com sucesso, False caso contrário
        """
        if await self.check_session_health():
            return True
        
        logger.info("Sessão não está saudável, tentando reconectar...")
        return await self.reconnect_with_retry(function_declarations)
    
    async def reconnect_with_retry(self, function_declarations: Optional[List[Dict[str, Any]]] = None) -> bool:
        """
        Reconecta com tentativas múltiplas e backoff exponencial
        
        Args:
            function_declarations: Declarações de função para a nova sessão
            
        Returns:
            True se reconectou com sucesso, False caso contrário
        """
        for attempt in range(self._max_reconnect_attempts):
            try:
                logger.info(f"Tentativa de reconexão {attempt + 1}/{self._max_reconnect_attempts}")
                
                # Fechar sessão atual
                await self.close_session()
                
                # Aguardar com backoff exponencial
                delay = self._reconnect_delay * (2 ** attempt)
                await asyncio.sleep(delay)
                
                # Tentar reconectar
                await self.start_audio_session(function_declarations)
                
                if self._is_connected:
                    logger.info(f"Reconexão bem-sucedida na tentativa {attempt + 1}")
                    self._connection_errors = 0
                    return True
                    
            except Exception as e:
                logger.error(f"Tentativa de reconexão {attempt + 1} falhou: {e}")
                self._connection_errors += 1
        
        logger.error(f"Falha em todas as {self._max_reconnect_attempts} tentativas de reconexão")
        return False
    
    async def reconnect(self, function_declarations: Optional[List[Dict[str, Any]]] = None) -> bool:
        """
        Reconecta a sessão em caso de falha
        
        Args:
            function_declarations: Declarações de função para a nova sessão
            
        Returns:
            True se reconectou com sucesso, False caso contrário
        """
        try:
            logger.info("Tentando reconectar sessão Gemini...")
            await self.close_session()
            
            # Aguardar um pouco antes de reconectar
            await asyncio.sleep(1)
            
            await self.start_audio_session(function_declarations)
            
            logger.info("Reconexão bem-sucedida")
            return True
            
        except Exception as e:
            logger.error(f"Falha na reconexão: {e}")
            return False 