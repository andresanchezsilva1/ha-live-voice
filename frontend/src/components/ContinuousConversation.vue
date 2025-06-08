<template>
  <div class="continuous-conversation">
    <!-- Status principal -->
    <div class="conversation-status">
      <div 
        class="status-indicator" 
        :class="`status-${statusColor}`"
        :title="statusText"
      >
        <div class="status-pulse" v-if="conversationState === 'listening'"></div>
        <i :class="statusIcon"></i>
      </div>
      
      <div class="status-info">
        <h3 class="status-title">{{ statusText }}</h3>
        <p class="status-details" v-if="vadState.isListening">
          Volume: {{ Math.round(vadState.volume * 100) }}%
        </p>
      </div>
    </div>

    <!-- Controles principais -->
    <div class="conversation-controls">
      <!-- Botão principal: Start/Stop conversa -->
      <button 
        v-if="!isConnected"
        @click="startConversation"
        class="btn btn-primary btn-large"
        :disabled="isStarting"
      >
        <i class="fas fa-play"></i>
        {{ isStarting ? 'Iniciando...' : 'Iniciar Conversa' }}
      </button>

      <!-- Controles durante conversa -->
      <div v-else class="active-controls">
        <!-- Botão Mute/Unmute principal -->
        <button 
          @click="toggleMute"
          class="btn btn-mute"
          :class="{ 'muted': isMuted }"
          title="Mutar/Desmutar microfone"
        >
          <i :class="isMuted ? 'fas fa-microphone-slash' : 'fas fa-microphone'"></i>
          {{ isMuted ? 'Desmutar' : 'Mutar' }}
        </button>

        <!-- Parar conversa -->
        <button 
          @click="stopConversation"
          class="btn btn-secondary"
          title="Parar conversa"
        >
          <i class="fas fa-stop"></i>
          Parar
        </button>

        <!-- Botão de debug para testar VAD -->
        <button 
          @click="forceRestartVAD"
          class="btn btn-debug"
          title="Forçar reinício do VAD (debug)"
          v-if="isConnected"
        >
          <i class="fas fa-sync-alt"></i>
          Reiniciar VAD
        </button>
      </div>
    </div>

    <!-- Volume do assistente -->
    <div class="volume-control" v-if="isConnected">
      <label class="volume-label">
        <i class="fas fa-volume-up"></i>
        Volume do Assistente
      </label>
      <div class="volume-slider">
        <input 
          type="range" 
          min="0" 
          max="1" 
          step="0.1"
          v-model="assistantVolume"
          @input="setAssistantVolume(Number($event.target.value))"
          class="slider"
        >
        <span class="volume-value">{{ Math.round(assistantVolume * 100) }}%</span>
      </div>
      
      <button 
        @click="toggleAssistantMute"
        class="btn btn-small"
        :class="{ 'muted': playbackState.isMuted }"
        title="Mutar/Desmutar assistente"
      >
        <i :class="playbackState.isMuted ? 'fas fa-volume-mute' : 'fas fa-volume-up'"></i>
      </button>
    </div>

    <!-- Configurações avançadas (collapsible) -->
    <details class="advanced-settings" v-if="isConnected">
      <summary>Configurações Avançadas</summary>
      
      <div class="settings-grid">
        <div class="setting-item">
          <label>Sensibilidade do Microfone</label>
          <input 
            type="range" 
            min="0.005" 
            max="0.05" 
            step="0.005"
            :value="vadConfig.volumeThreshold"
            @input="updateVadSensitivity(Number($event.target.value))"
            class="slider"
          >
          <span>{{ Math.round(vadConfig.volumeThreshold * 1000) / 10 }}%</span>
        </div>

        <div class="setting-item">
          <label>Tempo de Silêncio (ms)</label>
          <input 
            type="range" 
            min="500" 
            max="3000" 
            step="100"
            :value="vadConfig.silenceTimeout"
            @input="updateSilenceTimeout(Number($event.target.value))"
            class="slider"
          >
          <span>{{ vadConfig.silenceTimeout }}ms</span>
        </div>

        <div class="setting-item">
          <label>Confirmação de Voz (ms)</label>
          <input 
            type="range" 
            min="100" 
            max="500" 
            step="50"
            :value="vadConfig.voiceTimeout"
            @input="updateVoiceTimeout(Number($event.target.value))"
            class="slider"
          >
          <span>{{ vadConfig.voiceTimeout }}ms</span>
        </div>
      </div>
    </details>

    <!-- Visual feedback: Volume meter -->
    <div class="volume-meter" v-if="vadState.isListening">
      <div class="meter-label">Nível do Microfone</div>
      <div class="meter-bar">
        <div 
          class="meter-fill"
          :style="{ width: `${vadState.volume * 100}%` }"
          :class="{ 'active': vadState.isSpeaking }"
        ></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useContinuousConversation } from '../composables/useContinuousConversation'

// Props
interface Props {
  wsUrl?: string
  autoStart?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  wsUrl: 'ws://localhost:8000/ws',
  autoStart: false
})

// Estado local
const isStarting = ref(false)

// Inicializar conversa contínua
const conversation = useContinuousConversation({
  wsUrl: props.wsUrl,
  autoConnect: props.autoStart,
  vadConfig: {
    volumeThreshold: 0.008,
    silenceTimeout: 2500,
    voiceTimeout: 300
  }
})

// Desestruturar para facilitar uso no template
const {
  conversationState,
  isMuted,
  isConnected,
  assistantVolume,
  canSpeak,
  statusText,
  statusColor,
  vadState,
  playbackState,
  startConversation: startConv,
  stopConversation,
  toggleMute,
  setAssistantVolume,
  toggleAssistantMute,
  updateVadConfig,
  forceSpeaking,
  cleanup
} = conversation

// Acessar configuração VAD
const vadConfig = computed(() => conversation.vadState.value)

// Ícone do status
const statusIcon = computed(() => {
  switch (conversationState.value) {
    case 'listening':
      return 'fas fa-ear-listen'
    case 'speaking':
      return 'fas fa-microphone'
    case 'processing':
      return 'fas fa-spinner fa-spin'
    case 'assistant_speaking':
      return 'fas fa-volume-up'
    case 'muted':
      return 'fas fa-microphone-slash'
    default:
      return 'fas fa-power-off'
  }
})

// Métodos locais
const startConversation = async () => {
  try {
    isStarting.value = true
    await startConv()
  } catch (error) {
    console.error('Erro ao iniciar conversa:', error)
  } finally {
    isStarting.value = false
  }
}

const updateVadSensitivity = (value: number) => {
  updateVadConfig({ volumeThreshold: value })
}

const updateSilenceTimeout = (value: number) => {
  updateVadConfig({ silenceTimeout: value })
}

const updateVoiceTimeout = (value: number) => {
  updateVadConfig({ voiceTimeout: value })
}

// Função de debug para testar VAD
const forceRestartVAD = async () => {
  try {
    console.log('🔧 [DEBUG] Forçando reinício do VAD...')
    
    // Reiniciar a conversa completa (que reinicia o VAD)
    await stopConversation()
    await new Promise(resolve => setTimeout(resolve, 500))
    await startConversation()
    
    console.log('✅ [DEBUG] Conversa reiniciada com sucesso')
  } catch (error) {
    console.error('❌ [DEBUG] Erro ao reiniciar conversa:', error)
  }
}

// Lifecycle
onMounted(() => {
  if (props.autoStart) {
    startConversation()
  }
})

onUnmounted(() => {
  cleanup()
})
</script>

<style scoped>
.continuous-conversation {
  max-width: 600px;
  margin: 0 auto;
  padding: 2rem;
  background: white;
  border-radius: 16px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
}

.conversation-status {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 2rem;
  padding: 1.5rem;
  background: #f8fafc;
  border-radius: 12px;
}

.status-indicator {
  position: relative;
  width: 60px;
  height: 60px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5rem;
  color: white;
  transition: all 0.3s ease;
}

.status-pulse {
  position: absolute;
  top: -5px;
  left: -5px;
  right: -5px;
  bottom: -5px;
  border-radius: 50%;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.1); opacity: 0.7; }
  100% { transform: scale(1); opacity: 1; }
}

.status-blue { background: #3b82f6; }
.status-green { background: #10b981; }
.status-yellow { background: #f59e0b; }
.status-purple { background: #8b5cf6; }
.status-gray { background: #6b7280; }

.status-blue .status-pulse { background: rgba(59, 130, 246, 0.3); }
.status-green .status-pulse { background: rgba(16, 185, 129, 0.3); }

.status-info {
  flex: 1;
}

.status-title {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
  color: #1f2937;
}

.status-details {
  margin: 0.25rem 0 0 0;
  font-size: 0.875rem;
  color: #6b7280;
}

.conversation-controls {
  margin-bottom: 2rem;
}

.active-controls {
  display: flex;
  gap: 1rem;
  justify-content: center;
}

.btn {
  border: none;
  border-radius: 8px;
  padding: 0.75rem 1.5rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  background: #3b82f6;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: #2563eb;
}

.btn-large {
  padding: 1rem 2rem;
  font-size: 1.125rem;
}

.btn-mute {
  background: #10b981;
  color: white;
}

.btn-mute:hover {
  background: #059669;
}

.btn-mute.muted {
  background: #ef4444;
}

.btn-mute.muted:hover {
  background: #dc2626;
}

.btn-secondary {
  background: #6b7280;
  color: white;
}

.btn-secondary:hover {
  background: #4b5563;
}

.btn-debug {
  background: #f59e0b;
  color: white;
  font-size: 0.875rem;
}

.btn-debug:hover {
  background: #d97706;
}

.btn-small {
  padding: 0.5rem 1rem;
  font-size: 0.875rem;
}

.volume-control {
  margin-bottom: 1.5rem;
  padding: 1rem;
  background: #f8fafc;
  border-radius: 8px;
}

.volume-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 500;
  color: #374151;
  margin-bottom: 0.5rem;
}

.volume-slider {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.slider {
  flex: 1;
  height: 6px;
  border-radius: 3px;
  background: #d1d5db;
  outline: none;
  cursor: pointer;
}

.slider::-webkit-slider-thumb {
  appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #3b82f6;
  cursor: pointer;
}

.volume-value {
  min-width: 3rem;
  text-align: center;
  font-weight: 500;
  color: #374151;
}

.advanced-settings {
  margin-bottom: 1.5rem;
}

.advanced-settings summary {
  cursor: pointer;
  font-weight: 500;
  color: #374151;
  padding: 0.5rem 0;
}

.settings-grid {
  display: grid;
  gap: 1rem;
  margin-top: 1rem;
}

.setting-item {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.setting-item label {
  min-width: 150px;
  font-size: 0.875rem;
  color: #374151;
}

.setting-item span {
  min-width: 4rem;
  text-align: center;
  font-size: 0.875rem;
  color: #6b7280;
}

.volume-meter {
  margin-top: 1rem;
  padding: 1rem;
  background: #f1f5f9;
  border-radius: 8px;
}

.meter-label {
  font-size: 0.875rem;
  color: #475569;
  margin-bottom: 0.5rem;
}

.meter-bar {
  height: 8px;
  background: #e2e8f0;
  border-radius: 4px;
  overflow: hidden;
}

.meter-fill {
  height: 100%;
  background: #3b82f6;
  transition: width 0.1s ease;
  border-radius: 4px;
}

.meter-fill.active {
  background: #10b981;
}
</style> 