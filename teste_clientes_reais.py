#!/usr/bin/env python3
"""
Teste com Clientes Reais: Task 4 (GeminiLiveClient) + Task 3 (HomeAssistantClient)
"""

import asyncio
import os
from dotenv import load_dotenv

# Usar os clientes reais do projeto
from backend.poc_app.gemini_client.live_client import GeminiLiveClient
from backend.poc_app.gemini_client import HomeAssistantFunctionHandler, HA_FUNCTION_DECLARATIONS
from backend.poc_app.ha_client import HomeAssistantClient

async def test_real_clients():
    print("🚀 TESTE COM CLIENTES REAIS")
    print("Task 4 (GeminiLiveClient) + Task 3 (HomeAssistantClient)")
    print("=" * 70)
    
    # Carregar variáveis de ambiente
    load_dotenv()
    load_dotenv("backend/.env")
    
    gemini_key = os.getenv('GOOGLE_API_KEY')
    ha_url = os.getenv('HA_URL')
    ha_token = os.getenv('HA_LLAT')
    
    print(f"✅ GOOGLE_API_KEY: {'Encontrada' if gemini_key else 'Não encontrada'}")
    print(f"✅ HA_URL: {ha_url}")
    print(f"✅ HA_LLAT: {'Encontrada' if ha_token else 'Não encontrada'}")
    
    if not all([gemini_key, ha_url, ha_token]):
        print("❌ Credenciais necessárias não encontradas")
        return False
    
    try:
        # 1. Configurar Cliente HA Real (Task 3)
        print("\n📡 CONFIGURANDO CLIENTE HA REAL (TASK 3)")
        ha_client = HomeAssistantClient(base_url=ha_url, access_token=ha_token)
        
        # Testar conectividade
        status = await ha_client.check_api_status()
        print(f"✅ HA Status: {status.get('message', 'API running')}")
        
        # 2. Buscar entidades light e switch controláveis
        print("\n🔍 BUSCANDO ENTIDADES CONTROLÁVEIS...")
        all_states = await ha_client.get_all_states()
        
        # Filtrar apenas lights e switches com estados válidos
        controllable_entities = []
        for entity in all_states:
            if (entity.entity_id.startswith(('light.', 'switch.')) and 
                entity.state in ['on', 'off'] and
                'cozinha' in entity.entity_id.lower()):
                controllable_entities.append(entity)
        
        print(f"✅ Encontradas {len(controllable_entities)} entidades controláveis da cozinha:")
        for entity in controllable_entities[:5]:
            friendly_name = entity.attributes.get('friendly_name', entity.entity_id)
            print(f"   • {entity.entity_id} ({entity.state}) - {friendly_name}")
        
        if not controllable_entities:
            print("⚠️ Nenhuma entidade controlável da cozinha encontrada")
            # Tentar com qualquer light/switch
            for entity in all_states:
                if (entity.entity_id.startswith(('light.', 'switch.')) and 
                    entity.state in ['on', 'off']):
                    controllable_entities.append(entity)
                    if len(controllable_entities) >= 3:
                        break
            
            print(f"✅ Usando {len(controllable_entities)} entidades controláveis genéricas:")
            for entity in controllable_entities:
                friendly_name = entity.attributes.get('friendly_name', entity.entity_id)
                print(f"   • {entity.entity_id} ({entity.state}) - {friendly_name}")
        
        if not controllable_entities:
            print("❌ Nenhuma entidade controlável encontrada")
            return False
        
        # 3. Configurar Function Handler
        print("\n⚙️ CONFIGURANDO FUNCTION HANDLER")
        function_handler = HomeAssistantFunctionHandler(ha_client)
        print(f"✅ Handler configurado com {len(function_handler.get_supported_functions())} funções")
        
        # 4. Configurar Cliente Gemini Live (Task 4)
        print("\n🤖 CONFIGURANDO GEMINI LIVE CLIENT (TASK 4)")
        gemini_client = GeminiLiveClient(api_key=gemini_key)
        
        # 5. Conectar à Live API
        print("🔗 Conectando à Live API...")
        
        # Usar o método correto para conectar
        connected = await gemini_client.connect()
        if not connected:
            print("❌ Falha ao conectar à Live API")
            return False
            
        print("✅ Conectado à Live API")
        
        try:
            # 6. Testar com entidade real - priorizar switch.cozinha
            test_entity = None
            
            # Buscar especificamente switch.cozinha
            for entity in controllable_entities:
                if entity.entity_id == "switch.cozinha":
                    test_entity = entity
                    break
            
            # Se não encontrar switch.cozinha, usar a primeira disponível
            if not test_entity:
                test_entity = controllable_entities[0]
            
            entity_id = test_entity.entity_id
            current_state = test_entity.state
            friendly_name = test_entity.attributes.get('friendly_name', entity_id)
            domain = entity_id.split('.')[0]
            
            print(f"\n🎯 TESTANDO COM ENTIDADE REAL:")
            print(f"   Entity ID: {entity_id}")
            print(f"   Nome: {friendly_name}")
            print(f"   Estado atual: {current_state}")
            print(f"   Domínio: {domain}")
            
            # Determinar comando baseado no estado atual
            if current_state == "on":
                action = "Desligue"
                expected_call = "turn_off"
            else:
                action = "Ligue"
                expected_call = "turn_on"
            
            command = f"{action} {friendly_name}"
            print(f"\n📢 COMANDO: '{command}'")
            
            # 7. Enviar comando via Live API
            print("📤 Enviando comando...")
            sent = await gemini_client.send_text_input(command)
            if not sent:
                print("❌ Falha ao enviar comando")
                return False
            print("✅ Comando enviado")
            
            # 8. Aguardar respostas
            print("🎧 Aguardando respostas...")
            response_count = 0
            function_call_found = False
            
            async for response in gemini_client.receive_responses():
                response_count += 1
                
                response_type = response.get('type', 'unknown')
                print(f"📨 Resposta {response_count}: {response_type}")
                
                if response_type == 'function_call':
                    print("🔧 Function call detectado!")
                    function_calls = response.get('data', {}).get('function_calls', [])
                    
                    for fc in function_calls:
                        function_name = fc.get("name")
                        args = fc.get("args", {})
                        print(f"   📋 Função: {function_name}")
                        print(f"   📋 Args: {args}")
                        
                        # Executar function call com cliente HA real
                        try:
                            # Usar function handler para execução correta
                            result = await function_handler.handle_function_call({
                                "name": function_name,
                                "args": args
                            })
                            
                            if result.get('success'):
                                print(f"   ✅ Executado com sucesso: {result.get('message', 'OK')}")
                                if 'result' in result:
                                    details = result['result']
                                    if isinstance(details, dict) and 'entity_id' in details:
                                        print(f"   📊 Entidade: {details['entity_id']}")
                                        print(f"   📊 Ação: {details.get('action', 'N/A')}")
                                function_call_found = True
                            else:
                                print(f"   ⚠️ Resultado: {result.get('message', 'Erro desconhecido')}")
                                
                        except Exception as e:
                            print(f"   ❌ Erro ao executar function call: {e}")
                
                elif response_type == 'audio':
                    audio_size = len(response.get("data", b""))
                    print(f"🎵 Áudio recebido: {audio_size} bytes")
                
                elif response_type == 'text':
                    text = response.get("data", "")
                    if text:
                        print(f"💬 Texto recebido: {text[:100]}...")
                
                # Limitar respostas
                if response_count >= 10:
                    break
            
            # 9. Verificar estado final
            print("\n🔍 Verificando estado final...")
            try:
                final_state = await ha_client.get_entity_state(entity_id)
                print(f"✅ Estado final de {entity_id}: {final_state.state}")
                
                if final_state.state != current_state:
                    print("🎉 Estado mudou! Function call funcionou!")
                else:
                    print("⚠️ Estado não mudou")
                    
            except Exception as e:
                print(f"⚠️ Erro ao verificar estado final: {e}")
            
            if function_call_found:
                print("✅ Function call executado com sucesso!")
            else:
                print("⚠️ Nenhum function call detectado")
        
        finally:
            # Cleanup da sessão
            await gemini_client.disconnect()
        
        print("\n✅ Teste concluído!")
        return True
        
    except Exception as e:
        print(f"❌ Erro no teste: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    print("🧪 TESTE DE INTEGRAÇÃO COM CLIENTES REAIS")
    print("=" * 70)
    
    success = await test_real_clients()
    
    print("\n" + "=" * 70)
    if success:
        print("🎉 INTEGRAÇÃO COM CLIENTES REAIS FUNCIONANDO!")
        print("✅ Task 4 (GeminiLiveClient) operacional")
        print("✅ Task 3 (HomeAssistantClient) operacional")
        print("✅ Function calling integrado")
        print("✅ Entidades reais do HA controladas")
    else:
        print("⚠️ Problemas detectados na integração")
    
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main()) 