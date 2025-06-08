#!/usr/bin/env python3
import asyncio
import websockets
import json
import logging

logging.basicConfig(level=logging.INFO)

async def test_websocket():
    try:
        print('🔌 Conectando ao WebSocket...')
        async with websockets.connect('ws://localhost:8000/ws/voice') as websocket:
            print('✅ Conectado com sucesso!')
            
            # Teste 1: Ping
            ping_msg = json.dumps({'type': 'ping', 'data': 'test'})
            print(f'📤 Enviando ping: {ping_msg}')
            await websocket.send(ping_msg)
            
            response = await websocket.recv()
            print(f'📥 Resposta ping: {response}')
            
            # Teste 2: Mensagem de texto
            text_msg = json.dumps({'type': 'text', 'text': 'Olá servidor!', 'metadata': {'source': 'test'}})
            print(f'📤 Enviando texto: {text_msg}')
            await websocket.send(text_msg)
            
            response = await websocket.recv()
            print(f'📥 Resposta texto: {response}')
            
            # Teste 3: Request de info de conexão
            info_msg = json.dumps({'type': 'connection_info_request'})
            print(f'📤 Enviando request de info: {info_msg}')
            await websocket.send(info_msg)
            
            response = await websocket.recv()
            print(f'📥 Info da conexão: {response}')
            
    except Exception as e:
        print(f'❌ Erro: {e}')

if __name__ == "__main__":
    asyncio.run(test_websocket()) 