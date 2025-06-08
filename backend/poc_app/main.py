# backend/poc_app/main.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from .core.config import settings
import logging
import uvicorn

# Configurar logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Criar aplicação FastAPI
app = FastAPI(
    title="Home Assistant Voice Control POC",
    description="POC para controle do Home Assistant com Gemini Live API e interface Vue3",
    version="0.1.0",
    debug=settings.DEBUG
)

# Configurar CORS para permitir conexões do frontend Vue3
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://localhost:8080"],  # URLs típicas do Vue dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Endpoint raiz para verificar se a API está funcionando."""
    return {
        "message": "Home Assistant Voice Control POC API",
        "status": "running",
        "version": "0.1.0"
    }


@app.get("/health")
async def health_check():
    """Endpoint de health check para monitoramento."""
    return {
        "status": "healthy",
        "gemini_api_configured": bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "sua_chave_gemini_aqui"),
        "ha_configured": bool(settings.HA_URL and settings.HA_LLAT and settings.HA_LLAT != "seu_token_home_assistant_aqui"),
        "audio_config": {
            "sample_rate": settings.AUDIO_SAMPLE_RATE_GEMINI,
            "channels": settings.AUDIO_CHANNELS_GEMINI
        }
    }


@app.websocket("/ws/voice")
async def websocket_voice_endpoint(websocket: WebSocket):
    """
    Endpoint WebSocket principal para comunicação de voz com o frontend.
    Este será expandido nas próximas fases para integrar Gemini Live API e Home Assistant.
    """
    await websocket.accept()
    logger.info("Cliente WebSocket (Frontend Vue3) conectado.")
    
    try:
        while True:
            # Receber dados do frontend Vue3
            data = await websocket.receive()
            
            # Por enquanto, apenas fazer echo dos dados recebidos
            if data.get("type") == "text":
                message = data.get("text", "")
                logger.info(f"Mensagem recebida: {message}")
                await websocket.send_json({
                    "type": "response", 
                    "message": f"Echo: {message}",
                    "timestamp": "2025-06-08T00:00:00Z"
                })
            elif data.get("type") == "bytes":
                # Dados de áudio recebidos
                audio_data = data.get("bytes")
                logger.info(f"Dados de áudio recebidos: {len(audio_data)} bytes")
                await websocket.send_json({
                    "type": "audio_received",
                    "size": len(audio_data),
                    "message": "Áudio recebido com sucesso"
                })
            else:
                logger.warning(f"Tipo de dados desconhecido: {data.get('type')}")
                
    except WebSocketDisconnect:
        logger.info("Cliente WebSocket (Frontend Vue3) desconectado.")
    except Exception as e:
        logger.error(f"Erro no WebSocket: {e}", exc_info=True)


if __name__ == "__main__":
    # Executar servidor de desenvolvimento
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    ) 