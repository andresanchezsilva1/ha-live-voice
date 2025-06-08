"""
Handler para processar function calls do Gemini Live e executá-las via Home Assistant
"""

import logging
from typing import Any, Dict, Optional, Union
from .ha_functions import get_function_by_name, get_all_function_names

logger = logging.getLogger(__name__)


class HomeAssistantFunctionHandler:
    """
    Handler para processar function calls do Gemini e mapear para comandos do Home Assistant
    """
    
    def __init__(self, ha_client):
        """
        Inicializa o handler com uma instância do cliente Home Assistant
        
        Args:
            ha_client: Instância do cliente Home Assistant (implementado na task 3)
        """
        self.ha_client = ha_client
        self.supported_functions = get_all_function_names()
        logger.info(f"Handler inicializado com {len(self.supported_functions)} funções suportadas")
    
    async def handle_function_call(self, function_call: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processa uma function call do Gemini e executa a ação correspondente no Home Assistant
        
        Args:
            function_call: Dicionário com name e args da função a ser executada
            
        Returns:
            Dicionário com resultado da execução
        """
        function_name = function_call.get("name")
        function_args = function_call.get("args", {})
        
        if not function_name:
            return self._create_error_response("Nome da função não fornecido")
        
        if function_name not in self.supported_functions:
            return self._create_error_response(f"Função '{function_name}' não suportada")
        
        logger.info(f"Executando função: {function_name} com args: {function_args}")
        
        try:
            # Mapear função para método do cliente Home Assistant
            result = await self._execute_function(function_name, function_args)
            
            return {
                "success": True,
                "function_name": function_name,
                "result": result,
                "message": f"Função {function_name} executada com sucesso"
            }
            
        except Exception as e:
            logger.error(f"Erro ao executar função {function_name}: {e}")
            return self._create_error_response(f"Erro na execução: {str(e)}")
    
    async def _execute_function(self, function_name: str, args: Dict[str, Any]) -> Any:
        """
        Executa a função específica mapeando para o método correto do cliente HA
        
        Args:
            function_name: Nome da função a executar
            args: Argumentos da função
            
        Returns:
            Resultado da execução
        """
        # Mapeamento de funções para métodos do cliente Home Assistant (Tarefa 3)
        function_mapping = {
            # Controle de luzes
            "control_light": self._handle_light_control,
            
            # Controle de interruptores  
            "control_switch": self._handle_switch_control,
            
            # Controle de cenas
            "activate_scene": self._handle_scene_activation,
            
            # Controle de clima
            "control_climate": self._handle_climate_control,
            
            # Controle de mídia
            "control_media_player": self._handle_media_control,
            
            # Consulta de sensores
            "get_sensor_state": self._handle_sensor_query,
            
            # Consulta de estados gerais
            "get_entity_state": self._handle_entity_state_query,
            "list_entities": self._handle_list_entities,
            
            # Controle de coberturas
            "control_cover": self._handle_cover_control,
            
            # Controle de fechaduras
            "control_lock": self._handle_lock_control
        }
        
        handler = function_mapping.get(function_name)
        if not handler:
            raise ValueError(f"Handler não implementado para função: {function_name}")
        
        return await handler(args)
    
    async def _handle_light_control(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Handler para controle de luzes - Adaptado para métodos da Tarefa 3"""
        entity_id = args["entity_id"]
        action = args["action"]
        
        # Usar o método control_light da Tarefa 3: control_light(entity_id, state, brightness=None, color=None)
        if action == "turn_on":
            # Preparar parâmetros para control_light
            brightness = None
            color = None
            
            # Converter brightness_pct para brightness (0-255)
            if "brightness_pct" in args:
                brightness = int(args["brightness_pct"] * 255 / 100)
            elif "brightness" in args:
                brightness = args["brightness"]
                
            # Usar rgb_color se fornecido
            if "rgb_color" in args:
                color = args["rgb_color"]
            
            # Para kelvin e color_name, vamos precisar converter ou passar como atributos extras
            extra_params = {}
            if "kelvin" in args:
                extra_params["kelvin"] = args["kelvin"]
            if "color_name" in args:
                extra_params["color_name"] = args["color_name"]
            
            result = await self.ha_client.control_light(
                entity_id=entity_id, 
                state="on", 
                brightness=brightness, 
                color=color,
                **extra_params
            )
            
        elif action == "turn_off":
            result = await self.ha_client.control_light(entity_id, "off")
            
        elif action == "toggle":
            result = await self.ha_client.control_light(entity_id, "toggle")
        
        return {
            "entity_id": entity_id,
            "action": action,
            "status": "success",
            "details": result
        }
    
    async def _handle_switch_control(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Handler para controle de interruptores - Adaptado para métodos da Tarefa 3"""
        entity_id = args["entity_id"]
        action = args["action"]
        
        # Usar o método control_switch da Tarefa 3: control_switch(entity_id, state)
        if action == "turn_on":
            result = await self.ha_client.control_switch(entity_id, "on")
        elif action == "turn_off":
            result = await self.ha_client.control_switch(entity_id, "off")
        elif action == "toggle":
            result = await self.ha_client.control_switch(entity_id, "toggle")
        
        return {
            "entity_id": entity_id,
            "action": action,
            "status": "success",
            "details": result
        }
    
    async def _handle_scene_activation(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Handler para ativação de cenas - Adaptado para métodos da Tarefa 3"""
        entity_id = args["entity_id"]
        
        # Usar o método activate_scene da Tarefa 3: activate_scene(scene_id)
        result = await self.ha_client.activate_scene(entity_id)
        
        return {
            "entity_id": entity_id,
            "action": "activate",
            "status": "success",
            "details": result
        }
    
    async def _handle_climate_control(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Handler para controle de clima - Adaptado para métodos da Tarefa 3"""
        entity_id = args["entity_id"]
        action = args["action"]
        
        # Usar o método control_climate da Tarefa 3
        if action == "turn_on":
            result = await self.ha_client.control_climate(entity_id, action="turn_on")
        elif action == "turn_off":
            result = await self.ha_client.control_climate(entity_id, action="turn_off")
        elif action == "set_temperature":
            temperature = args["temperature"]
            result = await self.ha_client.control_climate(
                entity_id, action="set_temperature", temperature=temperature
            )
        elif action == "set_hvac_mode":
            hvac_mode = args["hvac_mode"]
            result = await self.ha_client.control_climate(
                entity_id, action="set_hvac_mode", hvac_mode=hvac_mode
            )
        
        return {
            "entity_id": entity_id,
            "action": action,
            "status": "success",
            "details": result
        }
    
    async def _handle_media_control(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Handler para controle de mídia - Adaptado para métodos da Tarefa 3"""
        entity_id = args["entity_id"]
        action = args["action"]
        
        # Usar o método control_media_player da Tarefa 3
        if action == "play":
            result = await self.ha_client.control_media_player(entity_id, action="play")
        elif action == "pause":
            result = await self.ha_client.control_media_player(entity_id, action="pause")
        elif action == "stop":
            result = await self.ha_client.control_media_player(entity_id, action="stop")
        elif action == "next_track":
            result = await self.ha_client.control_media_player(entity_id, action="next_track")
        elif action == "previous_track":
            result = await self.ha_client.control_media_player(entity_id, action="previous_track")
        elif action == "volume_up":
            result = await self.ha_client.control_media_player(entity_id, action="volume_up")
        elif action == "volume_down":
            result = await self.ha_client.control_media_player(entity_id, action="volume_down")
        elif action == "volume_set":
            volume_level = args["volume_level"]
            result = await self.ha_client.control_media_player(
                entity_id, action="volume_set", volume_level=volume_level
            )
        elif action == "mute":
            result = await self.ha_client.control_media_player(entity_id, action="mute")
        
        return {
            "entity_id": entity_id,
            "action": action,
            "status": "success",
            "details": result
        }
    
    async def _handle_sensor_query(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Handler para consulta de sensores - Compatível com Tarefa 3"""
        entity_id = args["entity_id"]
        
        # Usar get_entity_state que já existe na Tarefa 3
        result = await self.ha_client.get_entity_state(entity_id)
        
        return {
            "entity_id": entity_id,
            "action": "query",
            "status": "success",
            "state": result.get("state"),
            "attributes": result.get("attributes", {}),
            "last_changed": result.get("last_changed"),
            "last_updated": result.get("last_updated")
        }
    
    async def _handle_entity_state_query(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Handler para consulta de estado de entidades - Compatível com Tarefa 3"""
        entity_id = args["entity_id"]
        
        # Usar get_entity_state que já existe na Tarefa 3
        result = await self.ha_client.get_entity_state(entity_id)
        
        return {
            "entity_id": entity_id,
            "action": "query",
            "status": "success",
            "state": result.get("state"),
            "attributes": result.get("attributes", {}),
            "last_changed": result.get("last_changed"),
            "last_updated": result.get("last_updated")
        }
    
    async def _handle_list_entities(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Handler para listagem de entidades - Precisa ser implementado na Tarefa 3"""
        domain = args["domain"]
        area = args.get("area")
        
        # Este método precisa ser implementado na Tarefa 3
        # Vamos usar get_all_states() e filtrar por domínio como fallback
        try:
            if hasattr(self.ha_client, 'list_entities'):
                result = await self.ha_client.list_entities(domain, area)
            else:
                # Fallback: usar get_all_states e filtrar
                all_states = await self.ha_client.get_all_states()
                entities = [
                    entity for entity in all_states 
                    if entity.get("entity_id", "").startswith(f"{domain}.")
                ]
                if area:
                    # Filtrar por área se especificada
                    entities = [
                        entity for entity in entities
                        if entity.get("attributes", {}).get("area_id") == area
                    ]
                result = entities
        except Exception as e:
            logger.warning(f"Erro ao listar entidades: {e}. Usando fallback.")
            result = []
        
        return {
            "domain": domain,
            "area": area,
            "action": "list",
            "status": "success",
            "entities": result
        }
    
    async def _handle_cover_control(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Handler para controle de coberturas - Adaptado para métodos da Tarefa 3"""
        entity_id = args["entity_id"]
        action = args["action"]
        
        # Usar o método control_cover da Tarefa 3
        if action == "open_cover":
            result = await self.ha_client.control_cover(entity_id, action="open")
        elif action == "close_cover":
            result = await self.ha_client.control_cover(entity_id, action="close")
        elif action == "stop_cover":
            result = await self.ha_client.control_cover(entity_id, action="stop")
        elif action == "set_cover_position":
            position = args["position"]
            result = await self.ha_client.control_cover(
                entity_id, action="set_position", position=position
            )
        
        return {
            "entity_id": entity_id,
            "action": action,
            "status": "success",
            "details": result
        }
    
    async def _handle_lock_control(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Handler para controle de fechaduras - Adaptado para métodos da Tarefa 3"""
        entity_id = args["entity_id"]
        action = args["action"]
        
        # Usar call_service diretamente para locks (método genérico da Tarefa 3)
        if action == "lock":
            result = await self.ha_client.call_service("lock", "lock", {"entity_id": entity_id})
        elif action == "unlock":
            result = await self.ha_client.call_service("lock", "unlock", {"entity_id": entity_id})
        
        return {
            "entity_id": entity_id,
            "action": action,
            "status": "success",
            "details": result
        }
    
    def _create_error_response(self, error_message: str) -> Dict[str, Any]:
        """
        Cria uma resposta de erro padronizada
        
        Args:
            error_message: Mensagem de erro
            
        Returns:
            Dicionário com informações do erro
        """
        return {
            "success": False,
            "error": error_message,
            "function_name": None,
            "result": None
        }
    
    def get_supported_functions(self) -> list:
        """
        Retorna lista de funções suportadas
        
        Returns:
            Lista com nomes das funções suportadas
        """
        return self.supported_functions.copy()
    
    async def validate_function_call(self, function_call: Dict[str, Any]) -> Dict[str, Any]:
        """
        Valida uma function call antes da execução
        
        Args:
            function_call: Function call a ser validada
            
        Returns:
            Dicionário com resultado da validação
        """
        function_name = function_call.get("name")
        function_args = function_call.get("args", {})
        
        if not function_name:
            return {"valid": False, "error": "Nome da função não fornecido"}
        
        if function_name not in self.supported_functions:
            return {"valid": False, "error": f"Função '{function_name}' não suportada"}
        
        # Buscar declaração da função para validar argumentos
        function_declaration = get_function_by_name(function_name)
        if not function_declaration:
            return {"valid": False, "error": f"Declaração da função '{function_name}' não encontrada"}
        
        # Validar argumentos obrigatórios
        required_params = function_declaration["parameters"].get("required", [])
        missing_params = [param for param in required_params if param not in function_args]
        
        if missing_params:
            return {
                "valid": False, 
                "error": f"Parâmetros obrigatórios ausentes: {missing_params}"
            }
        
        return {"valid": True, "function_declaration": function_declaration} 