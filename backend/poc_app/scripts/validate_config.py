#!/usr/bin/env python3
"""
Script CLI para validar configuração da aplicação Home Assistant Voice Control
"""

import asyncio
import sys
import argparse
from pathlib import Path

# Adicionar diretório parent ao path para importar módulos
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from poc_app.core.config_validator import validate_app_config, ConfigValidator
from poc_app.models.config import ApplicationConfig


async def main():
    """Função principal do script"""
    parser = argparse.ArgumentParser(
        description="Validar configuração da aplicação Home Assistant Voice Control"
    )
    
    parser.add_argument(
        "--env-file",
        type=str,
        help="Caminho para arquivo .env (opcional)"
    )
    
    parser.add_argument(
        "--skip-connectivity",
        action="store_true",
        help="Pular testes de conectividade com serviços externos"
    )
    
    parser.add_argument(
        "--json",
        action="store_true",
        help="Exibir resultado em formato JSON"
    )
    
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Exibir apenas erros (modo silencioso)"
    )
    
    args = parser.parse_args()
    
    try:
        if not args.quiet:
            print("🔧 Validando configuração da aplicação...")
            print()
        
        # Validar configuração
        config = await validate_app_config(
            config_path=args.env_file,
            skip_connectivity=args.skip_connectivity
        )
        
        # Se chegou até aqui, configuração é válida
        if args.json:
            import json
            validator = ConfigValidator(config)
            results = await validator.validate_all(skip_connectivity=args.skip_connectivity)
            print(json.dumps(results, indent=2, ensure_ascii=False))
        elif not args.quiet:
            print("\n✅ Configuração válida e pronta para uso!")
            print(f"📱 Aplicação: {config.app_name} v{config.version}")
            print(f"🤖 Modelo Gemini: {config.gemini.model_name}")
            print(f"🏠 Home Assistant: {config.home_assistant.url}")
            print(f"🌐 WebSocket: {config.websocket.host}:{config.websocket.port}")
            print(f"📝 Log Level: {config.logging.level.value}")
        
        sys.exit(0)
        
    except SystemExit as e:
        # validate_app_config já lidou com os erros
        sys.exit(e.code)
    except Exception as e:
        if args.json:
            import json
            print(json.dumps({
                "error": True,
                "message": str(e),
                "valid": False
            }, indent=2))
        else:
            print(f"❌ Erro inesperado: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main()) 