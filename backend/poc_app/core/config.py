from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import os
from pathlib import Path


class Settings(BaseSettings):
    """
    Configurações da aplicação carregadas de variáveis de ambiente.
    Baseado no PRD seção 9.1 - Variáveis de Ambiente Necessárias.
    """
    
    # Gemini Live API Configuration
    GEMINI_API_KEY: str
    
    # Home Assistant Configuration  
    HA_URL: str
    HA_LLAT: str
    
    # Audio Configuration for Gemini
    AUDIO_SAMPLE_RATE_GEMINI: int = 16000  # Taxa de amostragem esperada pelo Gemini
    AUDIO_CHANNELS_GEMINI: int = 1         # Canais esperados pelo Gemini (mono)
    
    # Development Configuration (optional)
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    
    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent.parent / ".env",  # Caminho absoluto para o arquivo .env
        extra="ignore",
        case_sensitive=True
    )


# Instância global das configurações
settings = Settings() 