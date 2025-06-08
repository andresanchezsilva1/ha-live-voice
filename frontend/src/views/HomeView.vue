<template>
  <div class="home-view">
    <!-- Header -->
    <header class="app-header">
      <div class="header-content">
        <h1 class="app-title">
          <span class="title-icon">🏠</span>
          Home Assistant Voz
        </h1>
        
        <div class="connection-status" :class="{ 
          'connected': store.isConnected,
          'connecting': store.isConnecting,
          'error': store.hasError
        }">
          <div class="status-indicator"></div>
          <span class="status-text">
            {{ getConnectionStatusText() }}
          </span>
        </div>
      </div>
    </header>

    <!-- Loading inicial -->
    <Transition name="fade">
      <div v-if="store.isInitializing" class="loading-overlay">
        <div class="loading-spinner"></div>
        <p class="loading-text">Inicializando aplicação...</p>
      </div>
    </Transition>

          <!-- Conteúdo principal -->
    <main class="app-main" v-if="!store.isInitializing">
      
      <!-- Instruções iniciais quando não conectado -->
      <Transition name="fade">
        <div v-if="!store.isConnected && !store.isConnecting" class="welcome-section">
          <div class="welcome-container">
            <h2 class="welcome-title">
              <span class="welcome-icon">👋</span>
              Bem-vindo ao Assistente de Voz do Home Assistant
            </h2>
            <div class="welcome-content">
              <p class="welcome-description">
                Para começar a usar o assistente de voz, você precisa se conectar ao servidor.
                Isso permitirá que o navegador acesse seu microfone e reproduza áudio corretamente.
              </p>
              <div class="welcome-steps">
                <div class="step">
                  <span class="step-number">1</span>
                  <span class="step-text">Clique no botão "Conectar" abaixo</span>
                </div>
                <div class="step">
                  <span class="step-number">2</span>
                  <span class="step-text">Permita o acesso ao microfone quando solicitado</span>
                </div>
                <div class="step">
                  <span class="step-number">3</span>
                  <span class="step-text">Comece a gravar sua voz com o botão do microfone</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Transition>
      
      <!-- Modo de conversa contínua -->
      <div class="conversation-mode-section">
        <div class="mode-toggle">
          <label class="switch">
            <input 
              type="checkbox" 
              v-model="useContinuousMode"
              @change="handleModeToggle"
            >
            <span class="slider round"></span>
          </label>
          <span class="mode-label">
            {{ useContinuousMode ? 'Conversa Contínua' : 'Modo Manual' }}
          </span>
        </div>
      </div>

      <!-- Conversa contínua -->
      <div v-if="useContinuousMode" class="continuous-conversation-section">
        <ContinuousConversation 
          :ws-url="'ws://localhost:8000/ws'"
          :auto-start="false"
        />
      </div>

      <!-- Grid de componentes principais (modo manual) -->
      <div v-else class="content-grid">
        
        <div class="main-column">
          <!-- Área de transcrição -->
          <TranscriptionDisplay
            :transcription="store.transcription"
            :is-recording="store.isRecording"
            @clear="handleClearTranscription"
            @copy="handleCopyTranscription"
          />

          <!-- Resposta do sistema -->
          <SystemResponse
            :response="store.systemResponse"
            :is-playing="store.isPlaying"
            :is-processing="isProcessingResponse"
            @clear="handleClearResponse"
            @copy="handleCopyResponse"
          />
        </div>

        <div class="sidebar-column">
          <!-- Visualizador de áudio -->
          <div class="visualizer-section">
            <h2 class="section-title">
              <span class="section-icon">📊</span>
              Visualizador de Áudio
            </h2>
            <AudioVisualizer
              :media-stream="currentMediaStream"
              :is-recording="store.isRecording"
              :is-playing="store.isPlaying"
            />
          </div>

          <!-- Controles de áudio centralizados -->
          <section class="controls-section">
            <h2 class="section-title">
              <span class="section-icon">🎛️</span>
              Controles de Áudio
            </h2>
            
            <div class="audio-controls">
              <!-- Botão principal de gravação -->
              <button
                :class="['mic-button', { 
                  'active': store.isRecording,
                  'connecting': store.isConnecting,
                  'disabled': !store.canRecord && !store.isRecording,
                  'error': store.hasError
                }]"
                @click="handleToggleRecording"
                :disabled="store.isConnecting"
                :title="getMicButtonTooltip()"
              >
                <span class="mic-icon">
                  {{ getMicButtonIcon() }}
                </span>
                <span class="mic-text">
                  {{ getMicButtonText() }}
                </span>
                <div v-if="store.isRecording" class="recording-pulse"></div>
              </button>

              <!-- Controles avançados -->
              <div class="advanced-controls">
                <!-- Controles de volume -->
                <div class="volume-controls">
                  <button 
                    class="volume-button"
                    @click="audioWebSocket.toggleMute()"
                    :class="{ 'muted': store.isMuted }"
                    :title="store.isMuted ? 'Ativar som' : 'Silenciar'"
                  >
                    {{ store.isMuted ? '🔇' : '🔊' }}
                  </button>
                  
                  <div class="volume-slider-container">
                    <input
                      type="range"
                      class="volume-slider"
                      min="0"
                      max="1"
                      step="0.05"
                      :value="store.volume"
                      @input="handleVolumeChange"
                      :disabled="store.isMuted"
                      title="Volume do áudio"
                    />
                    <span class="volume-display">
                      {{ Math.round(store.volume * 100) }}%
                    </span>
                  </div>
                </div>

                <!-- Botões de ação -->
                <div class="action-buttons">
                  <button
                    v-if="!store.isConnected"
                    class="connect-button"
                    @click="handleConnect"
                    :disabled="store.isConnecting"
                    title="Conectar ao servidor"
                  >
                    <span class="button-icon">🔌</span>
                    {{ store.isConnecting ? 'Conectando...' : 'Conectar' }}
                  </button>
                  
                  <button
                    class="clear-button"
                    @click="handleClearAll"
                    :disabled="store.isRecording"
                    title="Limpar todas as mensagens"
                  >
                    <span class="button-icon">🗑️</span>
                    Limpar Tudo
                  </button>

                  <button
                    v-if="store.isConnected"
                    class="disconnect-button"
                    @click="handleDisconnect"
                    :disabled="store.isRecording"
                    title="Desconectar do servidor"
                  >
                    <span class="button-icon">🔌</span>
                    Desconectar
                  </button>
                </div>
              </div>
            </div>
          </section>
        </div>

      </div>

      <!-- Área de erro expandida -->
      <Transition name="slide-up">
        <section v-if="store.hasError" class="error-section">
          <div class="error-container">
            <div class="error-header">
              <span class="error-icon">⚠️</span>
              <h3 class="error-title">{{ store.error?.code }}</h3>
              <div class="error-actions">
                <button class="retry-button" @click="handleRetry" title="Tentar novamente">
                  🔄
                </button>
                <button class="error-close" @click="store.clearError()" title="Fechar erro">
                  ×
                </button>
              </div>
            </div>
            <div class="error-content">
              <p class="error-message">{{ store.error?.message }}</p>
              <p v-if="store.error?.details" class="error-details">{{ store.error.details }}</p>
              
              <!-- Sugestões de solução -->
              <div v-if="getErrorSuggestions().length > 0" class="error-suggestions">
                <h4>Sugestões:</h4>
                <ul>
                  <li v-for="suggestion in getErrorSuggestions()" :key="suggestion">
                    {{ suggestion }}
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </section>
      </Transition>

    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useAppStore } from '@/store/appStore'
import { useWebSocketAudio } from '@/composables/useWebSocketAudio'
import AudioVisualizer from '@/components/AudioVisualizer.vue'
import TranscriptionDisplay from '@/components/TranscriptionDisplay.vue'
import SystemResponse from '@/components/SystemResponse.vue'
import ContinuousConversation from '@/components/ContinuousConversation.vue'

// Store e composables
const store = useAppStore()
const wsUrl = 'ws://localhost:8000/ws'
const audioWebSocket = useWebSocketAudio(wsUrl)

// Estado local
const currentMediaStream = ref<MediaStream | null>(null)
const isProcessingResponse = ref(false)
const useContinuousMode = ref(false)

// Computed properties para textos dinâmicos
const getConnectionStatusText = () => {
  if (store.isConnecting) return 'Conectando...'
  if (store.isConnected) return 'Conectado'
  if (store.hasError) return 'Erro de conexão'
  return 'Desconectado'
}

const getMicButtonText = () => {
  if (store.isConnecting) return 'Conectando...'
  if (store.isRecording) return 'Parar Gravação'
  if (!store.isConnected) return 'Conectar Primeiro'
  return 'Iniciar Gravação'
}

const getMicButtonIcon = () => {
  if (store.isConnecting) return '⏳'
  if (store.isRecording) return '⏹️'
  if (store.hasError) return '❌'
  return '🎤'
}

const getMicButtonTooltip = () => {
  if (store.isConnecting) return 'Aguarde a conexão...'
  if (store.isRecording) return 'Clique para parar a gravação'
  if (!store.isConnected) return 'Conecte-se primeiro ao servidor'
  if (store.hasError) return 'Resolva o erro antes de continuar'
  return 'Clique para iniciar a gravação de voz'
}

// Manipuladores de eventos
const handleToggleRecording = async () => {
  try {
    if (!store.isConnected && !store.isRecording) {
      await handleConnect()
      return
    }
    
    if (store.isRecording) {
      await audioWebSocket.stopAudioRecording()
      currentMediaStream.value = null
    } else {
      // Obter MediaStream para visualização
      try {
        currentMediaStream.value = await navigator.mediaDevices.getUserMedia({
          audio: {
            channelCount: 1,
            sampleRate: 16000,
            echoCancellation: true,
            noiseSuppression: true
          }
        })
      } catch (error) {
        console.warn('Não foi possível obter MediaStream para visualização:', error)
      }
      
      await audioWebSocket.startAudioRecording()
    }
  } catch (error) {
    console.error('Erro ao alternar gravação:', error)
    store.setError('RECORDING_ERROR', 'Erro ao controlar gravação', (error as Error).message)
  }
}

const handleConnect = async () => {
  try {
    await audioWebSocket.connect()
  } catch (error) {
    console.error('Erro ao conectar:', error)
  }
}

const handleDisconnect = () => {
  try {
    audioWebSocket.disconnect()
    currentMediaStream.value = null
  } catch (error) {
    console.error('Erro ao desconectar:', error)
  }
}

const handleVolumeChange = (event: Event) => {
  const target = event.target as HTMLInputElement
  const volume = parseFloat(target.value)
  audioWebSocket.updateVolume(volume)
}

const handleClearAll = () => {
  audioWebSocket.clearAll()
  store.clearNotifications()
  store.clearError()
  currentMediaStream.value = null
}

const handleClearTranscription = () => {
  store.clearTranscription()
}

const handleClearResponse = () => {
  store.clearSystemResponse()
}

const handleCopyTranscription = (text: string) => {
  console.log('Transcrição copiada:', text)
}

const handleCopyResponse = (text: string) => {
  console.log('Resposta copiada:', text)
}

const handleModeToggle = () => {
  // Se estava no modo manual e está gravando, pare a gravação
  if (!useContinuousMode.value && store.isRecording) {
    audioWebSocket.stopAudioRecording()
  }
  
  // Se estava conectado no modo manual, desconecte
  if (!useContinuousMode.value && store.isConnected) {
    audioWebSocket.disconnect()
  }
  
  console.log('🔄 Modo alterado para:', useContinuousMode.value ? 'Conversa Contínua' : 'Manual')
}

const handleRetry = async () => {
  store.clearError()
  
  if (!store.isConnected) {
    await handleConnect()
  }
}

// Utilitários para UI
const getErrorSuggestions = () => {
  if (!store.error) return []
  
  const suggestions: string[] = []
  
  switch (store.error.code) {
    case 'WEBSOCKET_ERROR':
    case 'WEBSOCKET_CONNECTION_ERROR':
      suggestions.push('Verifique se o servidor está rodando')
      suggestions.push('Confirme se a URL do WebSocket está correta')
      suggestions.push('Verifique sua conexão com a internet')
      break
    case 'PERMISSION_DENIED':
      suggestions.push('Permita o acesso ao microfone nas configurações do navegador')
      suggestions.push('Recarregue a página e tente novamente')
      break
    case 'NO_MICROPHONE':
      suggestions.push('Conecte um microfone ao dispositivo')
      suggestions.push('Verifique se o microfone está funcionando')
      break
    case 'MICROPHONE_IN_USE':
      suggestions.push('Feche outros aplicativos que possam estar usando o microfone')
      suggestions.push('Reinicie o navegador se necessário')
      break
    default:
      suggestions.push('Tente recarregar a página')
      suggestions.push('Verifique se todos os serviços estão funcionando')
  }
  
  return suggestions
}

// Lifecycle hooks
onMounted(async () => {
  store.setInitializingStatus(true)
  
  try {
    // Remover conexão automática - aguardar ação do usuário
    // Isso permite que o navegador libere permissões de áudio corretamente
    store.addNotification('status', 'Aplicação carregada. Clique em "Conectar" para iniciar!')
  } catch (error) {
    console.error('Erro na inicialização:', error)
    store.setError('INIT_ERROR', 'Falha na inicialização da aplicação')
  } finally {
    store.setInitializingStatus(false)
  }
})

onUnmounted(() => {
  // Limpar MediaStream
  if (currentMediaStream.value) {
    currentMediaStream.value.getTracks().forEach(track => track.stop())
  }
  store.resetState()
})
</script>

<style scoped>
.home-view {
  display: grid;
  grid-template-rows: auto 1fr;
  height: 100%;
  width: 100%;
  background: #111827; /* Fundo escuro padrão */
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
  color: #d1d5db; /* Cor de texto claro */
}

/* Header */
.app-header {
  background: rgba(17, 24, 39, 0.8);
  backdrop-filter: blur(10px);
  box-shadow: 0 2px 20px rgba(0, 0, 0, 0.2);
  z-index: 100;
}

.header-content {
  padding: 1rem clamp(1.5rem, 4vw, 3rem);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.app-title {
  margin: 0;
  font-size: clamp(1.2rem, 3vw, 1.6rem);
  font-weight: 700;
  color: #818cf8;
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.title-icon {
  font-size: clamp(1.5rem, 3.5vw, 1.8rem);
}

/* Status de conexão */
.connection-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border-radius: 50px;
  background: #374151;
  border: 1px solid #4b5563;
  transition: all 0.3s ease;
  font-size: clamp(0.8rem, 2.5vw, 0.9rem);
  color: #e5e7eb;
}

.connection-status.connected {
  background: #059669;
  border-color: #10b981;
  color: white;
}

.connection-status.connecting {
  background: #d97706;
  border-color: #f59e0b;
  color: white;
}

.connection-status.error {
  background: #be123c;
  border-color: #ef4444;
  color: white;
}

.status-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  flex-shrink: 0;
}

.connection-status.connected .status-indicator {
  animation: pulse 2s infinite;
}

/* Loading */
.loading-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(17, 24, 39, 0.95);
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  z-index: 200;
}

.loading-spinner {
  width: clamp(30px, 8vw, 40px);
  height: clamp(30px, 8vw, 40px);
  border: 4px solid #374151;
  border-top: 4px solid #818cf8;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.loading-text {
  margin-top: 1rem;
  color: #9ca3af;
  font-size: clamp(0.9rem, 3vw, 1rem);
}

/* Main content - Layout */
.app-main {
  padding: clamp(1rem, 3vw, 2rem) clamp(1.5rem, 4vw, 3rem);
  overflow-y: auto;
}

.content-grid {
  display: grid;
  gap: clamp(1rem, 3vw, 2rem);
  grid-template-columns: 1fr;
}

.main-column, .sidebar-column {
  display: grid;
  gap: clamp(1rem, 3vw, 2rem);
  grid-template-columns: 1fr;
  grid-auto-rows: 1fr;
}

/* Seções */
.section-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0 0 1rem 0;
  font-size: clamp(1.1rem, 3.5vw, 1.2rem);
  font-weight: 600;
  color: #9ca3af;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.section-icon {
  font-size: clamp(1.2rem, 3.5vw, 1.3rem);
  flex-shrink: 0;
  color: #818cf8;
}

.visualizer-section, .controls-section {
  background: rgba(31, 41, 55, 0.6);
  border: 1px solid #4b5563;
  border-radius: 16px;
  padding: clamp(1rem, 3vw, 1.5rem);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  backdrop-filter: blur(10px);
  display: flex;
  flex-direction: column;
}

/* Controles */
.audio-controls {
  display: flex;
  flex-wrap: wrap;
  gap: clamp(1rem, 3vw, 2rem);
  align-items: center;
  justify-content: center;
  margin-top: auto;
}

.mic-button {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: clamp(100px, 15vw, 110px);
  height: clamp(100px, 15vw, 110px);
  border: 2px solid #4f46e5;
  border-radius: 50%;
  background: transparent;
  color: #a5b4fc;
  font-size: clamp(0.8rem, 2.5vw, 0.9rem);
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
  position: relative;
  overflow: hidden;
}

.mic-button:hover:not(:disabled) {
  background: #4f46e5;
  color: white;
  transform: scale(1.05);
  box-shadow: 0 0 25px rgba(79, 70, 229, 0.5);
}

.mic-button.active {
  background: #be123c;
  border-color: #f43f5e;
  color: white;
  animation: pulse-red 2s infinite;
}

.mic-button.connecting, .mic-button.disabled, .mic-button.error {
  opacity: 0.6;
  cursor: not-allowed;
  background: #374151;
  border-color: #4b5563;
  color: #9ca3af;
}

.mic-icon {
  font-size: clamp(1.8rem, 5vw, 2.2rem);
  margin-bottom: 0.5rem;
}

.mic-text {
  text-align: center;
}

.recording-pulse {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  border-radius: 50%;
  background: transparent;
  border: 2px solid #f43f5e;
  animation: ripple 1.5s infinite;
  pointer-events: none;
}

/* Controles avançados */
.advanced-controls {
  display: flex;
  flex-direction: column;
  gap: clamp(1rem, 2vw, 1.25rem);
  flex: 1;
}

/* Volume controls */
.volume-controls {
  display: flex;
  align-items: center;
  gap: clamp(0.5rem, 2vw, 1rem);
  padding: clamp(0.5rem, 2vw, 0.75rem);
  background: #1f2937;
  border: 1px solid #4b5563;
  border-radius: 12px;
}

.volume-button {
  padding: 0.5rem;
  border: none;
  background: none;
  font-size: clamp(1.2rem, 4vw, 1.5rem);
  cursor: pointer;
  border-radius: 8px;
  transition: background 0.2s;
  color: #9ca3af;
}

.volume-button:hover {
  background: #4b5563;
  color: white;
}

.volume-button.muted {
  color: #f43f5e;
}

.volume-slider-container {
  display: flex;
  align-items: center;
  gap: clamp(0.5rem, 2vw, 1rem);
  flex: 1;
}

.volume-slider {
  flex: 1;
  height: 6px;
  border-radius: 3px;
  background: #4b5563;
  outline: none;
  cursor: pointer;
  -webkit-appearance: none;
  appearance: none;
}

.volume-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #a5b4fc;
  cursor: pointer;
  transition: background 0.2s;
}
.volume-slider::-webkit-slider-thumb:hover {
  background: #818cf8;
}

.volume-slider::-moz-range-thumb {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #a5b4fc;
  cursor: pointer;
  border: none;
  transition: background 0.2s;
}
.volume-slider::-moz-range-thumb:hover {
  background: #818cf8;
}

.volume-display {
  font-size: clamp(0.8rem, 2.5vw, 0.9rem);
  color: #9ca3af;
  min-width: 40px;
  text-align: center;
}

/* Action buttons */
.action-buttons {
  display: flex;
  gap: clamp(0.5rem, 2vw, 0.75rem);
  justify-content: flex-start;
  flex-wrap: wrap;
}

.connect-button,
.clear-button,
.disconnect-button {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.6rem 1.2rem;
  border: 1px solid #4b5563;
  border-radius: 8px;
  font-weight: 600;
  font-size: clamp(0.8rem, 2.5vw, 0.9rem);
  cursor: pointer;
  transition: all 0.2s;
  background: #374151;
  color: #d1d5db;
}

.connect-button:hover:not(:disabled),
.disconnect-button:hover:not(:disabled),
.clear-button:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.2);
}

.connect-button { border-color: #10b981; }
.connect-button:hover:not(:disabled) { background-color: #10b981; color: white; }

.disconnect-button { border-color: #f59e0b; }
.disconnect-button:hover:not(:disabled) { background-color: #f59e0b; color: white; }

.clear-button { border-color: #6b7280; }
.clear-button:hover:not(:disabled) { background-color: #6b7280; color: white; }

/* Error section */
.error-section {
  background: rgba(190, 24, 93, 0.2);
  border: 1px solid #f43f5e;
  border-radius: 16px;
  padding: clamp(1rem, 3vw, 1.5rem);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  backdrop-filter: blur(10px);
}

.error-container {
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 12px;
  overflow: hidden;
}

.error-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: clamp(0.75rem, 2vw, 1rem);
  background: #fee2e2;
  border-bottom: 1px solid #fecaca;
  gap: 1rem;
}

.error-icon {
  font-size: clamp(1.2rem, 4vw, 1.5rem);
  flex-shrink: 0;
}

.error-title {
  margin: 0;
  color: #dc2626;
  font-size: clamp(0.9rem, 3vw, 1.1rem);
  flex: 1;
}

.error-actions {
  display: flex;
  gap: 0.5rem;
}

.retry-button,
.error-close {
  background: none;
  border: none;
  font-size: clamp(1rem, 3vw, 1.2rem);
  color: #dc2626;
  cursor: pointer;
  padding: 0.25rem;
  width: clamp(24px, 6vw, 28px);
  height: clamp(24px, 6vw, 28px);
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: background 0.2s;
}

.retry-button:hover,
.error-close:hover {
  background: rgba(220, 38, 38, 0.1);
}

.error-content {
  padding: clamp(0.75rem, 2vw, 1rem);
}

.error-message {
  margin: 0 0 0.5rem 0;
  color: #991b1b;
  font-weight: 600;
  font-size: clamp(0.85rem, 2.5vw, 0.95rem);
}

.error-details {
  margin: 0 0 1rem 0;
  color: #7f1d1d;
  font-size: clamp(0.8rem, 2.5vw, 0.9rem);
}

.error-suggestions {
  margin-top: 1rem;
}

.error-suggestions h4 {
  margin: 0 0 0.5rem 0;
  color: #991b1b;
  font-size: clamp(0.85rem, 2.5vw, 0.95rem);
}

.error-suggestions ul {
  margin: 0;
  padding-left: 1.2rem;
}

.error-suggestions li {
  color: #7f1d1d;
  font-size: clamp(0.8rem, 2.5vw, 0.85rem);
  margin-bottom: 0.25rem;
}

/* Mode toggle section */
.conversation-mode-section {
  margin-bottom: clamp(1.5rem, 4vw, 2rem);
  display: flex;
  justify-content: center;
}

.mode-toggle {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem 1.5rem;
  background: rgba(31, 41, 55, 0.5);
  border: 1px solid rgba(75, 85, 99, 0.3);
  border-radius: 16px;
  backdrop-filter: blur(10px);
}

.mode-label {
  font-size: 1.1rem;
  font-weight: 600;
  color: #e5e7eb;
}

/* Toggle Switch */
.switch {
  position: relative;
  display: inline-block;
  width: 60px;
  height: 34px;
}

.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #4b5563;
  transition: .4s;
}

.slider:before {
  position: absolute;
  content: "";
  height: 26px;
  width: 26px;
  left: 4px;
  bottom: 4px;
  background-color: white;
  transition: .4s;
}

input:checked + .slider {
  background-color: #10b981;
}

input:focus + .slider {
  box-shadow: 0 0 1px #10b981;
}

input:checked + .slider:before {
  transform: translateX(26px);
}

.slider.round {
  border-radius: 34px;
}

.slider.round:before {
  border-radius: 50%;
}

/* Continuous conversation section */
.continuous-conversation-section {
  margin-bottom: clamp(1.5rem, 4vw, 2rem);
}

/* Welcome section */
.welcome-section {
  margin-bottom: clamp(1.5rem, 4vw, 3rem);
}

.welcome-container {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.1), rgba(167, 243, 208, 0.1));
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 20px;
  padding: clamp(2rem, 5vw, 3rem);
  text-align: center;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.1);
  backdrop-filter: blur(10px);
}

.welcome-title {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  margin: 0 0 1.5rem 0;
  font-size: clamp(1.5rem, 4vw, 2rem);
  font-weight: 700;
  color: #a5b4fc;
  text-align: center;
}

.welcome-icon {
  font-size: clamp(2rem, 5vw, 2.5rem);
}

.welcome-description {
  font-size: clamp(1rem, 3vw, 1.1rem);
  color: #d1d5db;
  line-height: 1.6;
  margin: 0 0 2rem 0;
  max-width: 600px;
  margin-left: auto;
  margin-right: auto;
}

.welcome-steps {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  max-width: 500px;
  margin: 0 auto;
}

.step {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  background: rgba(31, 41, 55, 0.3);
  border: 1px solid rgba(75, 85, 99, 0.3);
  border-radius: 12px;
  text-align: left;
  transition: transform 0.2s ease;
}

.step:hover {
  transform: translateX(5px);
}

.step-number {
  display: flex;
  align-items: center;
  justify-content: center;
  width: clamp(32px, 8vw, 40px);
  height: clamp(32px, 8vw, 40px);
  background: #6366f1;
  color: white;
  border-radius: 50%;
  font-weight: 700;
  font-size: clamp(0.9rem, 2.5vw, 1rem);
  flex-shrink: 0;
}

.step-text {
  font-size: clamp(0.95rem, 2.8vw, 1rem);
  color: #e5e7eb;
  line-height: 1.4;
}

@media (max-width: 480px) {
  .welcome-steps {
    gap: 0.75rem;
  }
  
  .step {
    padding: 0.75rem;
    gap: 0.75rem;
  }
  
  .welcome-title {
    flex-direction: column;
    gap: 0.5rem;
  }
}

/* Animações */
@keyframes spin {
  to { transform: rotate(360deg); }
}

@keyframes pulse-red {
  0%, 100% { box-shadow: 0 0 0 0 rgba(244, 63, 94, 0.7); }
  50% { box-shadow: 0 0 0 10px rgba(244, 63, 94, 0); }
}

@keyframes pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.05); }
}

@keyframes ripple {
  to { transform: scale(4); opacity: 0; }
}

/* Transições */
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

.slide-up-enter-active, .slide-up-leave-active { transition: all 0.3s ease; }
.slide-up-enter-from, .slide-up-leave-to { opacity: 0; transform: translateY(20px); }

/* Responsive Design */
@media (min-width: 992px) {
  .content-grid {
    grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
  }
}

@media (max-width: 991px) {
  .main-column, .sidebar-column {
    grid-auto-rows: auto;
  }
  .audio-controls {
    flex-direction: column;
    margin-top: 1rem;
  }
  .advanced-controls {
    max-width: 400px;
    width: 100%;
  }
}

@media (max-width: 480px) {
  .header-content {
    padding: 0.75rem 1rem;
    flex-direction: column;
    gap: 0.75rem;
  }
  .app-main { padding: 1rem; }
  .volume-controls { flex-direction: column; align-items: stretch; }
  .action-buttons { flex-direction: column; align-items: stretch; }
  .action-buttons button { justify-content: center; }
}
</style> 