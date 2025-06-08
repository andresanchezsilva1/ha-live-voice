from enum import Enum
from typing import Dict, Any, Optional, Union, List
from pydantic import BaseModel, Field, validator
from datetime import datetime
import json
import logging
import base64

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    """Tipos de mensagens suportados pelo protocolo WebSocket"""
    
    # Mensagens de entrada (cliente -> servidor)
    TEXT = "text"
    AUDIO_DATA = "audio_data"
    BROADCAST_REQUEST = "broadcast_request"
    CONNECTION_INFO_REQUEST = "connection_info_request"
    PING = "ping"
    
    # Mensagens de saída (servidor -> cliente)
    RESPONSE = "response"
    AUDIO_RECEIVED = "audio_received"
    BROADCAST = "broadcast"
    BROADCAST_CONFIRMATION = "broadcast_confirmation"
    CONNECTION_INFO = "connection_info"
    STATUS_UPDATE = "status_update"
    ERROR = "error"
    PONG = "pong"


class AudioFormat(str, Enum):
    """Formatos de áudio suportados"""
    PCM_16_16000 = "pcm_16_16000"  # PCM 16-bit, 16kHz (padrão Gemini)
    WEBM_OPUS = "webm_opus"
    MP3 = "mp3"
    WAV = "wav"


class BaseMessage(BaseModel):
    """Classe base para todas as mensagens do protocolo"""
    
    type: MessageType
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    connection_id: Optional[str] = None
    message_id: Optional[str] = None
    
    class Config:
        use_enum_values = True


class TextMessage(BaseMessage):
    """Mensagem de texto do cliente"""
    
    type: MessageType = MessageType.TEXT
    text: str = Field(..., min_length=1, max_length=5000)
    metadata: Optional[Dict[str, Any]] = None


class AudioDataMessage(BaseMessage):
    """Mensagem de dados de áudio"""
    
    type: MessageType = MessageType.AUDIO_DATA
    audio_data: str = Field(..., description="Dados de áudio codificados em base64")
    format: AudioFormat = AudioFormat.PCM_16_16000
    duration_ms: Optional[int] = None
    sample_rate: int = 16000
    channels: int = 1
    
    @validator('audio_data')
    def validate_audio_data(cls, v):
        try:
            # Verificar se é base64 válido
            base64.b64decode(v)
            return v
        except Exception:
            raise ValueError("audio_data deve ser uma string base64 válida")


class BroadcastRequestMessage(BaseMessage):
    """Solicitação de broadcast para outras conexões"""
    
    type: MessageType = MessageType.BROADCAST_REQUEST
    message: str = Field(..., min_length=1, max_length=1000)
    exclude_sender: bool = True
    target_connections: Optional[List[str]] = None


class ConnectionInfoRequestMessage(BaseMessage):
    """Solicitação de informações de conexão"""
    
    type: MessageType = MessageType.CONNECTION_INFO_REQUEST


class PingMessage(BaseMessage):
    """Mensagem de ping para verificar conectividade"""
    
    type: MessageType = MessageType.PING
    data: Optional[str] = None


class ResponseMessage(BaseMessage):
    """Resposta do servidor para mensagem de texto"""
    
    type: MessageType = MessageType.RESPONSE
    message: str
    original_message: Optional[str] = None
    processing_time_ms: Optional[int] = None


class AudioReceivedMessage(BaseMessage):
    """Confirmação de recebimento de áudio"""
    
    type: MessageType = MessageType.AUDIO_RECEIVED
    size_bytes: int
    format: AudioFormat
    message: str = "Áudio recebido com sucesso"
    processing_time_ms: Optional[int] = None


class BroadcastMessage(BaseMessage):
    """Mensagem de broadcast para outros clientes"""
    
    type: MessageType = MessageType.BROADCAST
    message: str
    sender_id: str
    recipients_count: Optional[int] = None


class BroadcastConfirmationMessage(BaseMessage):
    """Confirmação de broadcast enviado"""
    
    type: MessageType = MessageType.BROADCAST_CONFIRMATION
    message: str
    recipients_count: int
    failed_count: int = 0


class ConnectionInfoMessage(BaseMessage):
    """Informações de conexão"""
    
    type: MessageType = MessageType.CONNECTION_INFO
    total_connections: int
    your_connection_id: str
    connected_at: str
    message_count: int
    last_activity: str


class StatusUpdateMessage(BaseMessage):
    """Atualização de status do sistema"""
    
    type: MessageType = MessageType.STATUS_UPDATE
    status: str
    message: str
    data: Optional[Dict[str, Any]] = None


class ErrorMessage(BaseMessage):
    """Mensagem de erro"""
    
    type: MessageType = MessageType.ERROR
    error_code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class PongMessage(BaseMessage):
    """Resposta de pong"""
    
    type: MessageType = MessageType.PONG
    data: Optional[str] = None


class MessageProtocol:
    """
    Protocolo de mensagens WebSocket estruturado.
    Gerencia serialização, deserialização e validação de mensagens.
    """
    
    # Mapeamento de tipos para classes
    MESSAGE_CLASSES = {
        MessageType.TEXT: TextMessage,
        MessageType.AUDIO_DATA: AudioDataMessage,
        MessageType.BROADCAST_REQUEST: BroadcastRequestMessage,
        MessageType.CONNECTION_INFO_REQUEST: ConnectionInfoRequestMessage,
        MessageType.PING: PingMessage,
        MessageType.RESPONSE: ResponseMessage,
        MessageType.AUDIO_RECEIVED: AudioReceivedMessage,
        MessageType.BROADCAST: BroadcastMessage,
        MessageType.BROADCAST_CONFIRMATION: BroadcastConfirmationMessage,
        MessageType.CONNECTION_INFO: ConnectionInfoMessage,
        MessageType.STATUS_UPDATE: StatusUpdateMessage,
        MessageType.ERROR: ErrorMessage,
        MessageType.PONG: PongMessage,
    }
    
    @classmethod
    def parse_message(cls, raw_data: Union[str, Dict, bytes]) -> Optional[BaseMessage]:
        """
        Deserializa dados brutos em uma mensagem estruturada.
        
        Args:
            raw_data: Dados recebidos do WebSocket
            
        Returns:
            BaseMessage: Mensagem deserializada ou None se inválida
        """
        try:
            # Converter para dict se necessário
            if isinstance(raw_data, str):
                data = json.loads(raw_data)
            elif isinstance(raw_data, bytes):
                data = json.loads(raw_data.decode('utf-8'))
            else:
                data = raw_data
            
            # Verificar se tem tipo
            message_type = data.get('type')
            if not message_type:
                logger.warning("Mensagem sem campo 'type'")
                return None
            
            # Buscar classe da mensagem
            message_class = cls.MESSAGE_CLASSES.get(message_type)
            if not message_class:
                logger.warning(f"Tipo de mensagem desconhecido: {message_type}")
                return None
            
            # Criar instância da mensagem
            return message_class(**data)
            
        except json.JSONDecodeError as e:
            logger.error(f"Erro ao decodificar JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Erro ao parsear mensagem: {e}")
            return None
    
    @classmethod
    def serialize_message(cls, message: BaseMessage) -> Dict[str, Any]:
        """
        Serializa uma mensagem estruturada para envio.
        
        Args:
            message: Mensagem a ser serializada
            
        Returns:
            Dict: Dados serializados para envio via WebSocket
        """
        try:
            return message.dict()
        except Exception as e:
            logger.error(f"Erro ao serializar mensagem: {e}")
            raise
    
    @classmethod
    def create_error_message(cls, error_code: str, message: str, 
                           connection_id: Optional[str] = None,
                           details: Optional[Dict[str, Any]] = None) -> ErrorMessage:
        """
        Cria uma mensagem de erro padronizada.
        
        Args:
            error_code: Código do erro
            message: Mensagem descritiva
            connection_id: ID da conexão (opcional)
            details: Detalhes adicionais (opcional)
            
        Returns:
            ErrorMessage: Mensagem de erro estruturada
        """
        return ErrorMessage(
            error_code=error_code,
            message=message,
            connection_id=connection_id,
            details=details
        )
    
    @classmethod
    def create_response_message(cls, message: str, connection_id: str,
                              original_message: Optional[str] = None,
                              processing_time_ms: Optional[int] = None) -> ResponseMessage:
        """
        Cria uma mensagem de resposta padronizada.
        
        Args:
            message: Conteúdo da resposta
            connection_id: ID da conexão
            original_message: Mensagem original (opcional)
            processing_time_ms: Tempo de processamento (opcional)
            
        Returns:
            ResponseMessage: Mensagem de resposta estruturada
        """
        return ResponseMessage(
            message=message,
            connection_id=connection_id,
            original_message=original_message,
            processing_time_ms=processing_time_ms
        )
    
    @classmethod
    def get_supported_message_types(cls) -> List[str]:
        """
        Retorna lista de tipos de mensagem suportados.
        
        Returns:
            List[str]: Tipos de mensagem suportados
        """
        return [msg_type.value for msg_type in MessageType]
    
    @classmethod
    def decode_audio_data(cls, audio_message: AudioDataMessage) -> bytes:
        """
        Decodifica dados de áudio de base64 para bytes.
        
        Args:
            audio_message: Mensagem de áudio
            
        Returns:
            bytes: Dados de áudio decodificados
        """
        try:
            return base64.b64decode(audio_message.audio_data)
        except Exception as e:
            logger.error(f"Erro ao decodificar áudio: {e}")
            raise ValueError("Dados de áudio inválidos")
    
    @classmethod
    def encode_audio_data(cls, audio_bytes: bytes) -> str:
        """
        Codifica dados de áudio binários para base64.
        
        Args:
            audio_bytes: Dados de áudio em bytes
            
        Returns:
            str: Dados codificados em base64
        """
        return base64.b64encode(audio_bytes).decode('utf-8') 