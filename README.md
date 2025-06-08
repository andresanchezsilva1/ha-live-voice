# Home Assistant Voice Control POC

Uma Prova de Conceito (POC) para controlar dispositivos do Home Assistant através de comandos de voz processados pela Gemini Live API do Google, com interface Vue3 moderna.

## 🎯 Objetivo

Desenvolver uma interface de voz natural e conversacional para automação residencial, utilizando:
- **Gemini Live API** para processamento de voz em tempo real
- **Home Assistant** para controle de dispositivos
- **Vue3 + TypeScript** para interface moderna
- **FastAPI** para backend robusto

## 🏗️ Arquitetura

```
ha-live-voice/
├── backend/                 # API FastAPI
│   ├── poc_app/
│   │   ├── main.py         # Aplicação principal
│   │   ├── core/           # Configurações
│   │   ├── gemini_client/  # Cliente Gemini Live API
│   │   ├── ha_client/      # Cliente Home Assistant
│   │   └── models/         # Modelos de dados
│   ├── tests/              # Testes backend
│   ├── requirements.txt    # Dependências Python
│   └── .env               # Variáveis de ambiente
├── frontend/               # Interface Vue3
│   ├── src/
│   │   ├── components/     # Componentes Vue
│   │   ├── composables/    # Composables
│   │   ├── store/          # Estado (Pinia)
│   │   └── views/          # Views/Páginas
│   └── tests/              # Testes frontend
└── README.md              # Este arquivo
```

## 🚀 Tecnologias

### Backend
- **Python 3.11+**
- **FastAPI** - Framework web moderno
- **google-genai** - SDK oficial do Gemini
- **WebSockets** - Comunicação em tempo real
- **Pydantic** - Validação de dados
- **httpx** - Cliente HTTP assíncrono

### Frontend
- **Vue 3** - Framework progressivo
- **TypeScript** - Tipagem estática
- **Vite** - Build tool rápido
- **Pinia** - Gerenciamento de estado
- **Vue Router** - Roteamento
- **vue-audio-visual** - Visualização de áudio

## 📋 Pré-requisitos

- **Python 3.11+**
- **Node.js 18+**
- **npm ou yarn**
- **Home Assistant** configurado e acessível
- **Chave API do Google Gemini**

## ⚙️ Configuração

### 1. Clone o repositório
```bash
git clone <repository-url>
cd ha-live-voice
```

### 2. Configuração do Backend

```bash
# Navegar para o diretório backend
cd backend

# Criar ambiente virtual Python
python3.11 -m venv venv

# Ativar ambiente virtual
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate     # Windows

# Instalar dependências
pip install -r requirements.txt

# Configurar variáveis de ambiente
cp .env.example .env
# Editar .env com suas configurações
```

### 3. Configuração do Frontend

```bash
# Navegar para o diretório frontend
cd frontend

# Instalar dependências
npm install

# Executar em modo desenvolvimento
npm run dev
```

## 🔧 Variáveis de Ambiente

Crie um arquivo `.env` no diretório `backend/` com:

```env
# Gemini Live API Configuration
GEMINI_API_KEY="sua_chave_gemini_aqui"

# Home Assistant Configuration  
HA_URL="http://homeassistant.local:8123"
HA_LLAT="seu_token_home_assistant_aqui"

# Audio Configuration for Gemini
AUDIO_SAMPLE_RATE_GEMINI=16000
AUDIO_CHANNELS_GEMINI=1

# Development Configuration
DEBUG=True
LOG_LEVEL=INFO
```

### Como obter as chaves:

1. **Gemini API Key**: 
   - Acesse [Google AI Studio](https://aistudio.google.com/)
   - Crie uma nova API key
   - Copie a chave para `GEMINI_API_KEY`

2. **Home Assistant Token**:
   - Acesse seu Home Assistant
   - Vá em Perfil → Tokens de Acesso de Longa Duração
   - Crie um novo token
   - Copie para `HA_LLAT`

## 🏃‍♂️ Executando o Projeto

### Backend (Terminal 1)
```bash
cd backend
source venv/bin/activate
cd poc_app
python main.py
```
O backend estará disponível em: http://localhost:8000

### Frontend (Terminal 2)
```bash
cd frontend
npm run dev
```
O frontend estará disponível em: http://localhost:5173

## 🧪 Testando

### Verificar Backend
```bash
curl http://localhost:8000/health
```

### Verificar Frontend
Acesse http://localhost:5173 no navegador

## 📚 Endpoints da API

- `GET /` - Status da aplicação
- `GET /health` - Health check com status das configurações
- `WebSocket /ws/voice` - Comunicação de voz em tempo real

## 🔄 Fluxo de Funcionamento

1. **Captura de Áudio**: Frontend captura áudio do microfone
2. **Streaming**: Áudio é enviado via WebSocket para o backend
3. **Processamento**: Backend envia áudio para Gemini Live API
4. **Interpretação**: Gemini processa comando e identifica ação
5. **Execução**: Backend executa comando no Home Assistant
6. **Resposta**: Resultado é enviado de volta ao frontend
7. **Feedback**: Frontend reproduz resposta de áudio/visual

## 🛠️ Desenvolvimento

### Estrutura de Comandos
```bash
# Backend
cd backend && source venv/bin/activate
python -m poc_app.main  # Executar aplicação
pytest tests/          # Executar testes

# Frontend  
cd frontend
npm run dev            # Desenvolvimento
npm run build          # Build produção
npm run test           # Executar testes
```

## 📝 Status do Projeto

- ✅ Estrutura básica do projeto
- ✅ Configuração do ambiente backend
- ✅ Configuração do ambiente frontend
- ⏳ Integração Gemini Live API
- ⏳ Integração Home Assistant
- ⏳ Captura e streaming de áudio
- ⏳ Interface de usuário completa

## 🤝 Contribuindo

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request

## 📄 Licença

Este projeto está sob a licença MIT. Veja o arquivo `LICENSE` para mais detalhes.

## 🆘 Suporte

Se encontrar problemas:

1. Verifique se todas as dependências estão instaladas
2. Confirme se as variáveis de ambiente estão configuradas
3. Verifique se o Home Assistant está acessível
4. Teste a conectividade com a Gemini API

Para mais ajuda, abra uma issue no repositório. 