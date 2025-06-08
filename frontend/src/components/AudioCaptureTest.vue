<template>
  <div class="audio-capture-test">
    <h2>Teste de Captura de Áudio</h2>
    
    <!-- Status da conexão -->
    <div class="status-section">
      <div class="status-item">
        <strong>Estado:</strong>
        <span :class="statusClass">{{ statusText }}</span>
      </div>
      
      <div class="status-item" v-if="isConnecting">
        <div class="loading-spinner"></div>
        <span>Conectando...</span>
      </div>
    </div>

    <!-- Controles -->
    <div class="controls-section">
      <button 
        @click="startCapture" 
        :disabled="isRecording || isConnecting || !browserSupported"
        class="btn btn-start"
      >
        {{ isRecording ? 'Gravando...' : 'Iniciar Gravação' }}
      </button>
      
      <button 
        @click="stopCapture" 
        :disabled="!isRecording"
        class="btn btn-stop"
      >
        Parar Gravação
      </button>
      
      <button 
        @click="testBrowserSupport" 
        class="btn btn-test"
      >
        Testar Suporte do Navegador
      </button>
    </div>

    <!-- Configurações de áudio -->
    <div class="config-section">
      <h3>Configurações de Áudio</h3>
      <div class="config-grid">
        <label>
          Sample Rate:
          <select v-model="audioConfig.sampleRate">
            <option value="8000">8000 Hz</option>
            <option value="16000">16000 Hz</option>
            <option value="44100">44100 Hz</option>
            <option value="48000">48000 Hz</option>
          </select>
        </label>
        
        <label>
          <input 
            type="checkbox" 
            v-model="audioConfig.echoCancellation"
          > 
          Echo Cancellation
        </label>
        
        <label>
          <input 
            type="checkbox" 
            v-model="audioConfig.noiseSuppression"
          > 
          Noise Suppression
        </label>
      </div>
    </div>

    <!-- WebSocket URL -->
    <div class="websocket-section">
      <label>
        WebSocket URL:
        <input 
          type="text" 
          v-model="websocketUrl" 
          placeholder="ws://localhost:8000/ws/voice"
          :disabled="isRecording"
        >
      </label>
    </div>

    <!-- Dispositivos de áudio -->
    <div class="devices-section" v-if="audioDevices.length > 0">
      <h3>Dispositivos de Áudio Disponíveis</h3>
      <ul class="devices-list">
        <li v-for="device in audioDevices" :key="device.deviceId">
          {{ device.label || `Microfone ${device.deviceId.substring(0, 8)}...` }}
        </li>
      </ul>
    </div>

    <!-- Visualização do MediaStream -->
    <div class="stream-info" v-if="mediaStream">
      <h3>Informações do Stream</h3>
      <div class="stream-details">
        <p><strong>Tracks ativos:</strong> {{ mediaStream.getTracks().length }}</p>
        <div v-for="track in mediaStream.getTracks()" :key="track.id" class="track-info">
          <p><strong>Track:</strong> {{ track.label || track.id }}</p>
          <p><strong>Estado:</strong> {{ track.readyState }}</p>
          <p><strong>Configurações:</strong></p>
          <pre>{{ JSON.stringify(track.getSettings(), null, 2) }}</pre>
        </div>
      </div>
    </div>

    <!-- Mensagens de erro -->
    <div class="error-section" v-if="error">
      <div class="error-message">
        <h3>❌ Erro</h3>
        <p><strong>Código:</strong> {{ error.code }}</p>
        <p><strong>Mensagem:</strong> {{ error.message }}</p>
        <p v-if="error.details"><strong>Detalhes:</strong> {{ error.details }}</p>
        <button @click="clearError" class="btn btn-clear">Limpar Erro</button>
      </div>
    </div>

    <!-- Log de eventos -->
    <div class="log-section">
      <h3>Log de Eventos</h3>
      <div class="log-container">
        <div 
          v-for="(log, index) in eventLogs" 
          :key="index" 
          class="log-entry"
          :class="log.type"
        >
          <span class="log-time">{{ log.timestamp }}</span>
          <span class="log-message">{{ log.message }}</span>
        </div>
      </div>
      <button @click="clearLogs" class="btn btn-clear">Limpar Logs</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useAudioCapture, type AudioCaptureConfig } from '../composables/useAudioCapture'

// Estado do componente
const websocketUrl = ref('ws://localhost:8000/ws/voice')
const audioDevices = ref<MediaDeviceInfo[]>([])
const eventLogs = ref<Array<{ timestamp: string, message: string, type: string }>>([])
const browserSupported = ref(false)

// Configuração de áudio reativa
const audioConfig = ref<AudioCaptureConfig>({
  channelCount: 1,
  sampleRate: 16000,
  echoCancellation: true,
  noiseSuppression: true
})

// Usar o composable de captura de áudio
const {
  isRecording,
  isConnecting,
  error,
  mediaStream,
  startRecording,
  stopRecording,
  clearError,
  getAudioDevices,
  checkBrowserSupport
} = useAudioCapture()

// Estados computados
const statusText = computed(() => {
  if (isRecording.value) return 'Gravando'
  if (isConnecting.value) return 'Conectando'
  if (error.value) return 'Erro'
  return 'Inativo'
})

const statusClass = computed(() => {
  if (isRecording.value) return 'status-recording'
  if (isConnecting.value) return 'status-connecting'
  if (error.value) return 'status-error'
  return 'status-inactive'
})

// Métodos
const addLog = (message: string, type: string = 'info') => {
  const timestamp = new Date().toLocaleTimeString()
  eventLogs.value.unshift({ timestamp, message, type })
  
  // Manter apenas os últimos 20 logs
  if (eventLogs.value.length > 20) {
    eventLogs.value = eventLogs.value.slice(0, 20)
  }
}

const startCapture = async () => {
  try {
    addLog('Iniciando captura de áudio...', 'info')
    await startRecording(websocketUrl.value, audioConfig.value)
    addLog('Captura de áudio iniciada com sucesso!', 'success')
  } catch (err: any) {
    addLog(`Erro ao iniciar captura: ${err.message}`, 'error')
  }
}

const stopCapture = async () => {
  addLog('Parando captura de áudio...', 'info')
  await stopRecording()
  addLog('Captura de áudio parada completamente', 'success')
}

const testBrowserSupport = () => {
  const supported = checkBrowserSupport()
  browserSupported.value = supported
  
  if (supported) {
    addLog('✅ Navegador suporta todas as APIs necessárias', 'success')
  } else {
    addLog('❌ Navegador não suporta algumas APIs necessárias', 'error')
  }
}

const loadAudioDevices = async () => {
  try {
    const devices = await getAudioDevices()
    audioDevices.value = devices
    addLog(`${devices.length} dispositivos de áudio encontrados`, 'info')
  } catch (err: any) {
    addLog(`Erro ao carregar dispositivos: ${err.message}`, 'error')
  }
}

const clearLogs = () => {
  eventLogs.value = []
}

// Inicialização
onMounted(async () => {
  testBrowserSupport()
  await loadAudioDevices()
  addLog('Componente de teste inicializado', 'info')
})
</script>

<style scoped>
.audio-capture-test {
  max-width: 800px;
  margin: 20px auto;
  padding: 20px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

.status-section, .controls-section, .config-section, 
.websocket-section, .devices-section, .stream-info, 
.error-section, .log-section {
  margin-bottom: 24px;
  padding: 16px;
  border: 1px solid #e1e5e9;
  border-radius: 8px;
  background-color: #fafbfc;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.status-recording { color: #d73a49; font-weight: bold; }
.status-connecting { color: #fb8500; font-weight: bold; }
.status-error { color: #d73a49; font-weight: bold; }
.status-inactive { color: #6a737d; }

.loading-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid #e1e5e9;
  border-top: 2px solid #0366d6;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.controls-section {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.btn {
  padding: 8px 16px;
  border: 1px solid #d1d5da;
  border-radius: 6px;
  background-color: #fafbfc;
  color: #24292e;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.btn:hover:not(:disabled) {
  background-color: #f3f4f6;
  border-color: #c6cbd1;
}

.btn:disabled {
  background-color: #f6f8fa;
  color: #959da5;
  cursor: not-allowed;
}

.btn-start:not(:disabled) {
  background-color: #28a745;
  color: white;
  border-color: #28a745;
}

.btn-stop:not(:disabled) {
  background-color: #dc3545;
  color: white;
  border-color: #dc3545;
}

.config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

.config-grid label {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.config-grid select, .config-grid input[type="text"] {
  padding: 6px 8px;
  border: 1px solid #d1d5da;
  border-radius: 4px;
}

.websocket-section input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #d1d5da;
  border-radius: 4px;
  font-family: 'Monaco', 'Menlo', monospace;
}

.devices-list {
  list-style: none;
  padding: 0;
}

.devices-list li {
  padding: 8px 12px;
  background-color: #f6f8fa;
  border: 1px solid #e1e5e9;
  border-radius: 4px;
  margin-bottom: 4px;
}

.stream-details {
  font-size: 14px;
}

.track-info {
  background-color: #f6f8fa;
  padding: 12px;
  border-radius: 4px;
  margin: 8px 0;
}

.track-info pre {
  background-color: #f1f3f4;
  padding: 8px;
  border-radius: 4px;
  font-size: 12px;
  overflow-x: auto;
}

.error-message {
  background-color: #ffeef0;
  border: 1px solid #fdaeb7;
  border-radius: 6px;
  padding: 16px;
  color: #86181d;
}

.log-container {
  max-height: 300px;
  overflow-y: auto;
  background-color: #f6f8fa;
  border: 1px solid #e1e5e9;
  border-radius: 4px;
  padding: 8px;
  margin-bottom: 12px;
}

.log-entry {
  display: flex;
  gap: 12px;
  padding: 4px 8px;
  font-size: 13px;
  font-family: 'Monaco', 'Menlo', monospace;
  border-radius: 3px;
  margin-bottom: 2px;
}

.log-entry.info { background-color: #e1f5fe; }
.log-entry.success { background-color: #e8f5e8; }
.log-entry.error { background-color: #ffeef0; }

.log-time {
  color: #6a737d;
  min-width: 80px;
}

.log-message {
  flex: 1;
}

h2, h3 {
  color: #24292e;
  margin-top: 0;
}
</style> 