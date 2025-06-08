from fastapi import WebSocket
import logging
from typing import List, Dict, Optional, Any
import uuid
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Gerenciador centralizado para múltiplas conexões WebSocket.
    
    Funcionalidades:
    - Rastrear conexões ativas com IDs únicos
    - Enviar mensagens para conexões específicas ou fazer broadcast
    - Gerenciar metadados das conexões (timestamps, contadores, etc.)
    - Fornecer estatísticas e informações de status
    """
    
    def __init__(self):
        # Dicionário principal: {connection_id: websocket}
        self.active_connections: Dict[str, WebSocket] = {}
        
        # Metadados das conexões: {connection_id: metadata}
        self.connection_metadata: Dict[str, Dict[str, Any]] = {}
    
    async def connect(self, websocket: WebSocket) -> str:
        """
        Aceita uma nova conexão WebSocket e gera um ID único.
        
        Args:
            websocket: Instância do WebSocket a ser registrada
            
        Returns:
            str: ID único gerado para a conexão
        """
        await websocket.accept()
        
        # Gerar ID único para a conexão
        connection_id = str(uuid.uuid4())
        
        # Registrar conexão e metadados
        self.active_connections[connection_id] = websocket
        self.connection_metadata[connection_id] = {
            "connected_at": datetime.utcnow().isoformat(),
            "message_count": 0,
            "last_activity": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Nova conexão WebSocket registrada: {connection_id}")
        return connection_id
    
    def disconnect(self, websocket: WebSocket) -> Optional[str]:
        """
        Remove uma conexão WebSocket baseada na instância do websocket.
        
        Args:
            websocket: Instância do WebSocket a ser removida
            
        Returns:
            Optional[str]: ID da conexão removida, ou None se não encontrada
        """
        connection_id = None
        
        # Encontrar o connection_id pela instância do websocket
        for conn_id, ws in self.active_connections.items():
            if ws == websocket:
                connection_id = conn_id
                break
        
        if connection_id:
            return self.disconnect_by_id(connection_id)
        
        logger.warning("Tentativa de desconectar WebSocket não registrado")
        return None
    
    def disconnect_by_id(self, connection_id: str) -> Optional[str]:
        """
        Remove uma conexão WebSocket baseada no ID da conexão.
        
        Args:
            connection_id: ID único da conexão a ser removida
            
        Returns:
            Optional[str]: ID da conexão removida, ou None se não encontrada
        """
        if connection_id in self.active_connections:
            # Remover da lista de conexões ativas
            del self.active_connections[connection_id]
            
            # Manter metadados por um tempo para histórico
            # (podem ser limpos por um processo de limpeza posterior)
            if connection_id in self.connection_metadata:
                self.connection_metadata[connection_id]["disconnected_at"] = datetime.utcnow().isoformat()
            
            logger.info(f"Conexão WebSocket removida: {connection_id}")
            return connection_id
        
        logger.warning(f"Tentativa de desconectar conexão inexistente: {connection_id}")
        return None
    
    async def send_to_connection(self, connection_id: str, message: Dict[str, Any]) -> bool:
        """
        Envia uma mensagem para uma conexão específica.
        
        Args:
            connection_id: ID único da conexão de destino
            message: Dados da mensagem a serem enviados
            
        Returns:
            bool: True se a mensagem foi enviada com sucesso, False caso contrário
        """
        if connection_id not in self.active_connections:
            logger.warning(f"Tentativa de enviar mensagem para conexão inexistente: {connection_id}")
            return False
        
        websocket = self.active_connections[connection_id]
        
        try:
            await websocket.send_json(message)
            
            # Atualizar metadados
            if connection_id in self.connection_metadata:
                self.connection_metadata[connection_id]["message_count"] += 1
                self.connection_metadata[connection_id]["last_activity"] = datetime.utcnow().isoformat()
            
            logger.debug(f"Mensagem enviada para conexão {connection_id}")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem para conexão {connection_id}: {e}")
            # Remover conexão problemática
            self.disconnect_by_id(connection_id)
            return False
    
    async def broadcast_message(self, message: Dict[str, Any], exclude_connections: Optional[List[str]] = None) -> int:
        """
        Envia uma mensagem para todas as conexões ativas (broadcast).
        
        Args:
            message: Dados da mensagem a serem enviados
            exclude_connections: Lista de IDs de conexões a serem excluídas do broadcast
            
        Returns:
            int: Número de conexões que receberam a mensagem com sucesso
        """
        if not self.active_connections:
            logger.info("Nenhuma conexão ativa para broadcast")
            return 0
        
        exclude_list = exclude_connections or []
        successful_sends = 0
        failed_connections = []
        
        # Criar lista de tarefas para envio paralelo
        send_tasks = []
        target_connections = []
        
        for connection_id in self.active_connections.keys():
            if connection_id not in exclude_list:
                target_connections.append(connection_id)
                # Clonar mensagem para cada conexão (para personalização futura)
                message_copy = message.copy()
                send_tasks.append(self.send_to_connection(connection_id, message_copy))
        
        if not send_tasks:
            logger.info("Nenhuma conexão elegível para broadcast após exclusões")
            return 0
        
        # Executar todos os envios em paralelo
        try:
            results = await asyncio.gather(*send_tasks, return_exceptions=True)
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    failed_connections.append(target_connections[i])
                    logger.error(f"Falha no broadcast para {target_connections[i]}: {result}")
                elif result:
                    successful_sends += 1
                else:
                    failed_connections.append(target_connections[i])
        
        except Exception as e:
            logger.error(f"Erro crítico durante broadcast: {e}")
        
        logger.info(f"Broadcast concluído: {successful_sends} sucessos, {len(failed_connections)} falhas")
        
        # Limpar conexões que falharam
        for failed_id in failed_connections:
            self.disconnect_by_id(failed_id)
        
        return successful_sends
    
    def get_connection_count(self) -> int:
        """
        Retorna o número atual de conexões ativas.
        
        Returns:
            int: Número de conexões ativas
        """
        return len(self.active_connections)
    
    def get_connection_info(self, connection_id: str) -> Optional[Dict[str, Any]]:
        """
        Retorna informações detalhadas de uma conexão específica.
        
        Args:
            connection_id: ID único da conexão
            
        Returns:
            Optional[Dict[str, Any]]: Metadados da conexão ou None se não encontrada
        """
        if connection_id not in self.connection_metadata:
            return None
        
        metadata = self.connection_metadata[connection_id].copy()
        metadata["is_active"] = connection_id in self.active_connections
        metadata["connection_id"] = connection_id
        
        return metadata
    
    def get_all_connections_info(self) -> Dict[str, Dict[str, Any]]:
        """
        Retorna informações detalhadas de todas as conexões (ativas e recentes).
        
        Returns:
            Dict[str, Dict[str, Any]]: Dicionário com metadados de todas as conexões
        """
        all_info = {}
        
        for connection_id, metadata in self.connection_metadata.items():
            info = metadata.copy()
            info["is_active"] = connection_id in self.active_connections
            info["connection_id"] = connection_id
            all_info[connection_id] = info
        
        return all_info
    
    def get_active_connection_ids(self) -> List[str]:
        """
        Retorna lista de IDs de todas as conexões ativas.
        
        Returns:
            List[str]: Lista de IDs das conexões ativas
        """
        return list(self.active_connections.keys())
    
    def is_connection_active(self, connection_id: str) -> bool:
        """
        Verifica se uma conexão específica está ativa.
        
        Args:
            connection_id: ID único da conexão
            
        Returns:
            bool: True se a conexão está ativa, False caso contrário
        """
        return connection_id in self.active_connections
    
    def cleanup_old_metadata(self, hours: int = 24) -> int:
        """
        Remove metadados de conexões antigas e inativas.
        
        Args:
            hours: Número de horas para considerar metadados como antigos
            
        Returns:
            int: Número de entradas removidas
        """
        cutoff_time = datetime.utcnow().timestamp() - (hours * 3600)
        connections_to_remove = []
        
        for connection_id, metadata in self.connection_metadata.items():
            # Pular conexões ativas
            if connection_id in self.active_connections:
                continue
            
            # Verificar se tem timestamp de desconexão
            if "disconnected_at" in metadata:
                try:
                    disconnected_time = datetime.fromisoformat(metadata["disconnected_at"]).timestamp()
                    if disconnected_time < cutoff_time:
                        connections_to_remove.append(connection_id)
                except ValueError:
                    # Se timestamp inválido, remover também
                    connections_to_remove.append(connection_id)
        
        # Remover metadados antigos
        for connection_id in connections_to_remove:
            del self.connection_metadata[connection_id]
        
        if connections_to_remove:
            logger.info(f"Limpeza de metadados: {len(connections_to_remove)} entradas antigas removidas")
        
        return len(connections_to_remove)
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Retorna estatísticas resumidas do gerenciador de conexões.
        
        Returns:
            Dict[str, Any]: Estatísticas do gerenciador
        """
        active_count = len(self.active_connections)
        total_tracked = len(self.connection_metadata)
        
        # Calcular total de mensagens enviadas
        total_messages = sum(
            metadata.get("message_count", 0) 
            for metadata in self.connection_metadata.values()
        )
        
        return {
            "active_connections": active_count,
            "total_tracked_connections": total_tracked,
            "inactive_connections": total_tracked - active_count,
            "total_messages_sent": total_messages,
            "average_messages_per_connection": total_messages / max(total_tracked, 1)
        } 