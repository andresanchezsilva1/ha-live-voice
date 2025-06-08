"""
Declarações de função para integração com Home Assistant
Estas funções permitem que o Gemini Live controle dispositivos do Home Assistant
"""

# Declarações de função para controle de luzes
LIGHT_FUNCTIONS = [
    {
        "name": "control_light",
        "description": "Controla uma entidade de luz no Home Assistant (ligar, desligar, ajustar brilho, cor, etc.)",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "O ID da entidade da luz (ex: light.sala_de_estar, light.quarto_principal)"
                },
                "action": {
                    "type": "string",
                    "enum": ["turn_on", "turn_off", "toggle"],
                    "description": "Ação a ser executada na luz"
                },
                "brightness": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 255,
                    "description": "Nível de brilho da luz (0-255). Usado apenas com turn_on."
                },
                "brightness_pct": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                    "description": "Nível de brilho em porcentagem (0-100%). Usado apenas com turn_on."
                },
                "rgb_color": {
                    "type": "array",
                    "items": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 255
                    },
                    "minItems": 3,
                    "maxItems": 3,
                    "description": "Cor RGB da luz como [R, G, B]. Usado apenas com turn_on."
                },
                "kelvin": {
                    "type": "integer",
                    "minimum": 2000,
                    "maximum": 6500,
                    "description": "Temperatura de cor em Kelvin. Usado apenas com turn_on."
                },
                "color_name": {
                    "type": "string",
                    "enum": ["red", "green", "blue", "yellow", "orange", "purple", "pink", "white", "warm_white", "cool_white"],
                    "description": "Nome da cor predefinida. Usado apenas com turn_on."
                }
            },
            "required": ["entity_id", "action"]
        }
    }
]

# Declarações de função para controle de interruptores
SWITCH_FUNCTIONS = [
    {
        "name": "control_switch", 
        "description": "Controla um interruptor ou tomada inteligente no Home Assistant",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "O ID da entidade do interruptor (ex: switch.ventilador_sala, switch.tomada_escritorio)"
                },
                "action": {
                    "type": "string",
                    "enum": ["turn_on", "turn_off", "toggle"],
                    "description": "Ação a ser executada no interruptor"
                }
            },
            "required": ["entity_id", "action"]
        }
    }
]

# Declarações de função para controle de cenas
SCENE_FUNCTIONS = [
    {
        "name": "activate_scene",
        "description": "Ativa uma cena predefinida no Home Assistant",
        "parameters": {
            "type": "object", 
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "O ID da entidade da cena (ex: scene.modo_filme, scene.jantar_romantico)"
                }
            },
            "required": ["entity_id"]
        }
    }
]

# Declarações de função para controle de clima/aquecimento
CLIMATE_FUNCTIONS = [
    {
        "name": "control_climate",
        "description": "Controla sistema de ar condicionado, aquecimento ou termostato no Home Assistant",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "O ID da entidade de clima (ex: climate.ar_condicionado_sala, climate.termostato_principal)"
                },
                "action": {
                    "type": "string", 
                    "enum": ["turn_on", "turn_off", "set_temperature", "set_hvac_mode"],
                    "description": "Ação a ser executada no sistema de clima"
                },
                "temperature": {
                    "type": "number",
                    "minimum": 10,
                    "maximum": 35,
                    "description": "Temperatura desejada em graus Celsius. Usado com set_temperature."
                },
                "hvac_mode": {
                    "type": "string",
                    "enum": ["heat", "cool", "auto", "off", "heat_cool", "fan_only", "dry"],
                    "description": "Modo de operação do HVAC. Usado com set_hvac_mode."
                }
            },
            "required": ["entity_id", "action"]
        }
    }
]

# Declarações de função para controle de mídia
MEDIA_FUNCTIONS = [
    {
        "name": "control_media_player",
        "description": "Controla players de mídia como Spotify, YouTube, TV, etc. no Home Assistant",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "O ID da entidade do media player (ex: media_player.spotify, media_player.tv_sala)"
                },
                "action": {
                    "type": "string",
                    "enum": ["play", "pause", "stop", "next_track", "previous_track", "volume_up", "volume_down", "volume_set", "mute"],
                    "description": "Ação a ser executada no media player"
                },
                "volume_level": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "Nível de volume (0.0 a 1.0). Usado com volume_set."
                }
            },
            "required": ["entity_id", "action"]
        }
    }
]

# Declarações de função para consulta de sensores
SENSOR_FUNCTIONS = [
    {
        "name": "get_sensor_state",
        "description": "Consulta o estado atual de um sensor no Home Assistant (temperatura, umidade, movimento, etc.)",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "O ID da entidade do sensor (ex: sensor.temperatura_sala, sensor.umidade_quarto)"
                }
            },
            "required": ["entity_id"]
        }
    }
]

# Declarações de função para consulta de estados gerais
STATE_FUNCTIONS = [
    {
        "name": "get_entity_state",
        "description": "Consulta o estado atual de qualquer entidade no Home Assistant",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "O ID de qualquer entidade no Home Assistant"
                }
            },
            "required": ["entity_id"]
        }
    },
    {
        "name": "list_entities",
        "description": "Lista entidades disponíveis no Home Assistant por domínio",
        "parameters": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "enum": ["light", "switch", "scene", "climate", "media_player", "sensor", "binary_sensor", "cover", "lock"],
                    "description": "Domínio das entidades a listar (ex: light para luzes, switch para interruptores)"
                },
                "area": {
                    "type": "string",
                    "description": "Nome da área/cômodo para filtrar entidades (opcional)"
                }
            },
            "required": ["domain"]
        }
    }
]

# Declarações de função para controle de coberturas (cortinas, persianas, etc.)
COVER_FUNCTIONS = [
    {
        "name": "control_cover",
        "description": "Controla coberturas como cortinas, persianas, portões no Home Assistant",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "O ID da entidade da cobertura (ex: cover.cortina_sala, cover.persiana_quarto)"
                },
                "action": {
                    "type": "string",
                    "enum": ["open_cover", "close_cover", "stop_cover", "set_cover_position"],
                    "description": "Ação a ser executada na cobertura"
                },
                "position": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                    "description": "Posição da cobertura em porcentagem (0=fechada, 100=aberta). Usado com set_cover_position."
                }
            },
            "required": ["entity_id", "action"]
        }
    }
]

# Declarações de função para controle de fechaduras
LOCK_FUNCTIONS = [
    {
        "name": "control_lock",
        "description": "Controla fechaduras inteligentes no Home Assistant",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "O ID da entidade da fechadura (ex: lock.porta_entrada, lock.portao_garagem)"
                },
                "action": {
                    "type": "string",
                    "enum": ["lock", "unlock"],
                    "description": "Ação a ser executada na fechadura"
                }
            },
            "required": ["entity_id", "action"]
        }
    }
]

# Lista completa de todas as declarações de função para Home Assistant
HA_FUNCTION_DECLARATIONS = (
    LIGHT_FUNCTIONS +
    SWITCH_FUNCTIONS + 
    SCENE_FUNCTIONS +
    CLIMATE_FUNCTIONS +
    MEDIA_FUNCTIONS +
    SENSOR_FUNCTIONS +
    STATE_FUNCTIONS +
    COVER_FUNCTIONS +
    LOCK_FUNCTIONS
)

# Mapeamento de domínios para facilitar organização
FUNCTION_DOMAINS = {
    "light": LIGHT_FUNCTIONS,
    "switch": SWITCH_FUNCTIONS,
    "scene": SCENE_FUNCTIONS,
    "climate": CLIMATE_FUNCTIONS,
    "media_player": MEDIA_FUNCTIONS,
    "sensor": SENSOR_FUNCTIONS,
    "cover": COVER_FUNCTIONS,
    "lock": LOCK_FUNCTIONS,
    "state": STATE_FUNCTIONS
}

def get_functions_for_domain(domain: str):
    """
    Retorna as declarações de função para um domínio específico
    
    Args:
        domain: Domínio do Home Assistant (light, switch, etc.)
        
    Returns:
        Lista de declarações de função para o domínio especificado
    """
    return FUNCTION_DOMAINS.get(domain, [])

def get_all_function_names():
    """
    Retorna uma lista com os nomes de todas as funções disponíveis
    
    Returns:
        Lista de strings com nomes das funções
    """
    return [func["name"] for func in HA_FUNCTION_DECLARATIONS]

def get_function_by_name(name: str):
    """
    Busca uma declaração de função pelo nome
    
    Args:
        name: Nome da função a buscar
        
    Returns:
        Dicionário com a declaração da função ou None se não encontrada
    """
    for func in HA_FUNCTION_DECLARATIONS:
        if func["name"] == name:
            return func
    return None 