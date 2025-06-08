"""
Validador de configuração para inicialização da aplicação
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from pathlib import Path
import aiohttp
import sys
import os

from ..models.config import ApplicationConfig
from pydantic import ValidationError

logger = logging.getLogger(__name__)


class ConfigValidator:
    """Validador de configuração da aplicação"""
    
    def __init__(self, config: ApplicationConfig):
        self.config = config
        self.validation_results: Dict[str, Any] = {}
    
    async def validate_all(self, skip_connectivity: bool = False) -> Dict[str, Any]:
        """
        Executa validação completa da configuração
        
        Args:
            skip_connectivity: Se True, pula testes de conectividade
            
        Returns:
            Dict com resultados detalhados da validação
        """
        logger.info("Iniciando validação completa da configuração")
        
        results = {
            "config_structure": {"valid": False, "errors": []},
            "environment_variables": {"valid": False, "missing": [], "invalid": []},
            "connectivity": {"valid": False, "services": {}},
            "overall": {"valid": False, "message": ""}
        }
        
        # 1. Validar estrutura da configuração (já feito pelo Pydantic)
        results["config_structure"] = self._validate_structure()
        
        # 2. Validar variáveis de ambiente
        results["environment_variables"] = self._validate_environment_variables()
        
        # 3. Validar conectividade (se solicitado)
        if not skip_connectivity:
            results["connectivity"] = await self._validate_connectivity()
        else:
            results["connectivity"]["valid"] = True
            results["connectivity"]["message"] = "Testes de conectividade ignorados"
        
        # 4. Determinar status geral
        overall_valid = (
            results["config_structure"]["valid"] and
            results["environment_variables"]["valid"] and
            results["connectivity"]["valid"]
        )
        
        results["overall"]["valid"] = overall_valid
        
        if overall_valid:
            results["overall"]["message"] = "Configuração válida e pronta para uso"
            logger.info("✅ Configuração validada com sucesso")
        else:
            results["overall"]["message"] = "Problemas encontrados na configuração"
            logger.error("❌ Falhas na validação da configuração")
        
        self.validation_results = results
        return results
    
    def _validate_structure(self) -> Dict[str, Any]:
        """Valida estrutura da configuração Pydantic"""
        try:
            # Se chegamos até aqui, o Pydantic já validou
            return {
                "valid": True,
                "errors": [],
                "message": "Estrutura da configuração válida"
            }
        except Exception as e:
            return {
                "valid": False,
                "errors": [str(e)],
                "message": f"Erro na estrutura: {str(e)}"
            }
    
    def _validate_environment_variables(self) -> Dict[str, Any]:
        """Valida se todas as variáveis de ambiente necessárias estão presentes"""
        required_vars = [
            "GEMINI_API_KEY",
            "HA_URL", 
            "HA_LLAT"
        ]
        
        optional_vars = [
            "GEMINI_MODEL",
            "GEMINI_MAX_TOKENS",
            "GEMINI_TEMPERATURE",
            "WS_HOST",
            "WS_PORT",
            "LOG_LEVEL",
            "LOG_FILE",
            "DEBUG"
        ]
        
        missing = []
        invalid = []
        
        # Verificar variáveis obrigatórias
        for var in required_vars:
            value = os.getenv(var)
            if not value:
                missing.append(var)
            elif var == "GEMINI_API_KEY" and not value.startswith("AIza"):
                invalid.append(f"{var}: formato inválido (deve começar com 'AIza')")
            elif var == "HA_URL" and not value.startswith(("http://", "https://")):
                invalid.append(f"{var}: deve ser uma URL válida")
            elif var == "HA_LLAT" and len(value) < 50:
                invalid.append(f"{var}: token muito curto")
        
        # Verificar variáveis opcionais se presentes
        for var in optional_vars:
            value = os.getenv(var)
            if value:  # Só valida se estiver presente
                try:
                    if var in ["GEMINI_MAX_TOKENS", "WS_PORT"]:
                        int(value)
                    elif var == "GEMINI_TEMPERATURE":
                        temp = float(value)
                        if not 0.0 <= temp <= 2.0:
                            invalid.append(f"{var}: deve estar entre 0.0 e 2.0")
                    elif var == "LOG_LEVEL":
                        if value.upper() not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
                            invalid.append(f"{var}: nível de log inválido")
                except ValueError:
                    invalid.append(f"{var}: formato numérico inválido")
        
        is_valid = len(missing) == 0 and len(invalid) == 0
        
        result = {
            "valid": is_valid,
            "missing": missing,
            "invalid": invalid
        }
        
        if is_valid:
            result["message"] = "Todas as variáveis de ambiente estão corretas"
        else:
            messages = []
            if missing:
                messages.append(f"Faltando: {', '.join(missing)}")
            if invalid:
                messages.append(f"Inválidas: {', '.join(invalid)}")
            result["message"] = "; ".join(messages)
        
        return result
    
    async def _validate_connectivity(self) -> Dict[str, Any]:
        """Valida conectividade com serviços externos"""
        logger.info("Testando conectividade com serviços externos")
        
        services = {}
        
        # Testar Home Assistant
        services["home_assistant"] = await self._test_home_assistant_connection()
        
        # Para Gemini, não podemos testar facilmente sem fazer uma chamada real
        services["gemini_api"] = self._test_gemini_api_format()
        
        # Determinar status geral
        all_services_ok = all(
            service.get("status") == "connected" 
            for service in services.values()
        )
        
        return {
            "valid": all_services_ok,
            "services": services,
            "message": "Todos os serviços acessíveis" if all_services_ok else "Problemas de conectividade detectados"
        }
    
    async def _test_home_assistant_connection(self) -> Dict[str, Any]:
        """Testa conexão com Home Assistant"""
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                headers = {
                    "Authorization": f"Bearer {self.config.home_assistant.access_token}",
                    "Content-Type": "application/json"
                }
                
                # Testar endpoint de API básico
                url = f"{self.config.home_assistant.url}/api/"
                
                async with session.get(url, headers=headers, ssl=self.config.home_assistant.verify_ssl) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "status": "connected",
                            "message": f"Home Assistant acessível (versão: {data.get('version', 'unknown')})",
                            "version": data.get('version'),
                            "response_time_ms": response.headers.get('X-Response-Time', 'unknown')
                        }
                    else:
                        return {
                            "status": "error",
                            "message": f"HTTP {response.status}: {response.reason}",
                            "code": response.status
                        }
                        
        except aiohttp.ClientConnectorError as e:
            return {
                "status": "unreachable",
                "message": f"Não foi possível conectar: {str(e)}",
                "error": str(e)
            }
        except asyncio.TimeoutError:
            return {
                "status": "timeout",
                "message": "Timeout na conexão (>10s)",
                "error": "Timeout"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Erro inesperado: {str(e)}",
                "error": str(e)
            }
    
    def _test_gemini_api_format(self) -> Dict[str, Any]:
        """Valida formato da API key do Gemini (sem fazer chamada real)"""
        api_key = self.config.gemini.api_key
        
        if api_key.startswith("AIza") and len(api_key) >= 30:
            return {
                "status": "connected",  # Assume que está OK baseado no formato
                "message": "Formato da API key válido",
                "validation": "format_only"
            }
        else:
            return {
                "status": "error",
                "message": "Formato da API key inválido",
                "validation": "format_failed"
            }
    
    def print_validation_summary(self, results: Optional[Dict[str, Any]] = None) -> None:
        """Imprime resumo da validação no console"""
        if not results:
            results = self.validation_results
        
        if not results:
            print("❌ Nenhuma validação executada")
            return
        
        print("\n" + "="*60)
        print("📋 RESUMO DA VALIDAÇÃO DE CONFIGURAÇÃO")
        print("="*60)
        
        # Status geral
        overall = results.get("overall", {})
        status_icon = "✅" if overall.get("valid") else "❌"
        print(f"\n{status_icon} Status Geral: {overall.get('message', 'Unknown')}")
        
        # Estrutura da configuração
        config_struct = results.get("config_structure", {})
        status_icon = "✅" if config_struct.get("valid") else "❌"
        print(f"\n{status_icon} Estrutura da Configuração")
        if config_struct.get("errors"):
            for error in config_struct["errors"]:
                print(f"   ❌ {error}")
        
        # Variáveis de ambiente
        env_vars = results.get("environment_variables", {})
        status_icon = "✅" if env_vars.get("valid") else "❌"
        print(f"\n{status_icon} Variáveis de Ambiente")
        
        if env_vars.get("missing"):
            print("   ❌ Faltando:")
            for var in env_vars["missing"]:
                print(f"      • {var}")
        
        if env_vars.get("invalid"):
            print("   ❌ Inválidas:")
            for var in env_vars["invalid"]:
                print(f"      • {var}")
        
        # Conectividade
        connectivity = results.get("connectivity", {})
        status_icon = "✅" if connectivity.get("valid") else "❌"
        print(f"\n{status_icon} Conectividade")
        
        services = connectivity.get("services", {})
        for service_name, service_data in services.items():
            service_status = service_data.get("status", "unknown")
            service_icon = "✅" if service_status == "connected" else "❌"
            service_message = service_data.get("message", "")
            print(f"   {service_icon} {service_name.replace('_', ' ').title()}: {service_message}")
        
        print("\n" + "="*60)
        
        # Sugestões se houver problemas
        if not overall.get("valid"):
            print("\n💡 SUGESTÕES PARA CORREÇÃO:")
            
            if env_vars.get("missing"):
                print("   • Configure as variáveis de ambiente faltando no arquivo .env")
                print("   • Verifique se o arquivo .env está no diretório correto")
            
            if env_vars.get("invalid"):
                print("   • Corrija os formatos das variáveis inválidas")
                print("   • Consulte a documentação para formatos esperados")
            
            if not connectivity.get("valid"):
                print("   • Verifique a conectividade de rede")
                print("   • Confirme se os serviços estão rodando")
                print("   • Verifique URLs e tokens de acesso")
            
            print()


async def validate_app_config(config_path: Optional[str] = None, 
                            skip_connectivity: bool = False) -> ApplicationConfig:
    """
    Função utilitária para validar configuração da aplicação
    
    Args:
        config_path: Caminho para arquivo .env (opcional)
        skip_connectivity: Pular testes de conectividade
        
    Returns:
        ApplicationConfig validada
        
    Raises:
        SystemExit: Se configuração for inválida
    """
    # Carregar variáveis do arquivo .env se especificado
    if config_path:
        from dotenv import load_dotenv
        load_dotenv(config_path)
    
    try:
        # Criar configuração a partir do ambiente
        config = ApplicationConfig.from_env()
        
        # Validar
        validator = ConfigValidator(config)
        results = await validator.validate_all(skip_connectivity=skip_connectivity)
        
        # Imprimir resumo
        validator.print_validation_summary(results)
        
        # Se inválida, sair
        if not results["overall"]["valid"]:
            logger.error("Configuração inválida - encerrando aplicação")
            sys.exit(1)
        
        return config
        
    except ValidationError as e:
        logger.error(f"Erro de validação Pydantic: {e}")
        print(f"\n❌ Erro na configuração: {e}")
        sys.exit(1)
    except ValueError as e:
        logger.error(f"Erro de configuração: {e}")
        print(f"\n❌ {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Erro inesperado na validação: {e}")
        print(f"\n❌ Erro inesperado: {e}")
        sys.exit(1) 