#!/usr/bin/env python3
import asyncio
import websockets
import json

async def test_simple():
    try:
        async with websockets.connect('ws://localhost:8000/ws/voice') as websocket:
            print('✅ Conectado')
            
            # Teste simples de ping
            ping_msg = {'type': 'ping', 'data': 'test'}
            print(f'📤 Enviando: {ping_msg}')
            await websocket.send(json.dumps(ping_msg))
            
            response = await websocket.recv()
            print(f'📥 Recebido: {response}')
            
    except Exception as e:
        print(f'❌ Erro: {e}')

if __name__ == "__main__":
    asyncio.run(test_simple()) 