<template>
  <div class="audio-playback-controls">
    <div class="controls-header">
      <h3>🔊 Controles de Áudio</h3>
      <div class="status-indicator" :class="{ 
        active: state.isPlaying,
        error: hasErrors,
        recovering: state.isRecovering
      }">
        {{ getStatusText() }}
      </div>
    </div>

    <!-- Error Section -->
    <div v-if="hasErrors" class="error-section">
      <div class="error-header">
        <h4>⚠️ Problemas Detectados</h4>
        <div class="error-stats">
          Erros: {{ state.errorCount }} | Saúde: {{ isHealthy ? 'Boa' : 'Ruim' }}
        </div>
      </div>
      
      <div v-if="state.lastError" class="error-details">
        <div class="error-type">{{ getErrorTypeText(state.lastError.type) }}</div>
        <div class="error-message">{{ state.lastError.message }}</div>
        <div class="error-time">{{ formatTime(state.lastError.timestamp) }}</div>
      </div>
      
      <div class="error-actions">
        <button @click="clearErrors" class="btn btn-warning">
          Limpar Erros
        </button>
        <button @click="recoverFromErrors" class="btn btn-success" :disabled="state.isRecovering">
          {{ state.isRecovering ? 'Recuperando...' : 'Recuperar Sistema' }}
        </button>
      </div>
      
      <div v-if="errorReport.recommendations.length > 0" class="recommendations">
        <h5>📋 Recomendações:</h5>
        <ul>
          <li v-for="rec in errorReport.recommendations" :key="rec">{{ rec }}</li>
        </ul>
      </div>
    </div>

    <!-- Queue Status -->
    <div class="queue-status">
      <div class="queue-info">
        <span class="queue-count">Fila: {{ state.queueLength }}</span>
        <span v-if="state.currentItem" class="current-playing">
          Tocando: {{ state.currentItem.id.slice(-8) }}
        </span>
        <span v-if="state.isRecovering" class="recovering-indicator">
          🔄 Recuperando...
        </span>
      </div>
      
      <div class="queue-actions">
        <button 
          @click="clearQueue" 
          :disabled="!hasItemsInQueue"
          class="btn btn-secondary"
        >
          Limpar Fila
        </button>
        
        <button 
          @click="state.isPlaying ? pauseQueue() : resumeQueue()" 
          :disabled="(!hasItemsInQueue && !state.isPlaying) || state.isRecovering"
          class="btn btn-primary"
        >
          {{ state.isPlaying ? 'Pausar' : 'Retomar' }}
        </button>
        
        <button 
          @click="stopPlayback" 
          :disabled="!state.isPlaying"
          class="btn btn-danger"
        >
          Parar
        </button>
      </div>
    </div>

    <!-- Volume Controls -->
    <div class="volume-controls">
      <label for="volume-slider">Volume:</label>
      <div class="volume-group">
        <input
          id="volume-slider"
          type="range"
          min="0"
          max="1"
          step="0.1"
          :value="state.volume"
          @input="handleVolumeChange"
          :disabled="state.isMuted"
          class="volume-slider"
        />
        <span class="volume-display">{{ Math.round(state.volume * 100) }}%</span>
        <button 
          @click="toggleMute" 
          class="btn btn-mute"
          :class="{ muted: state.isMuted }"
        >
          {{ state.isMuted ? '🔇' : '🔊' }}
        </button>
      </div>
    </div>

    <!-- Test Audio Section -->
    <div class="test-section">
      <h4>🎵 Teste de Áudio</h4>
      <div class="test-controls">
        <button @click="generateTestAudio" class="btn btn-test" :disabled="state.isRecovering">
          Gerar Áudio de Teste
        </button>
        <button @click="simulateMultipleAudios" class="btn btn-test" :disabled="state.isRecovering">
          Simular Múltiplos Áudios
        </button>
        <button @click="playSuccessSound" class="btn btn-test" :disabled="state.isRecovering">
          Som de Sucesso
        </button>
        <button @click="playErrorSound" class="btn btn-test" :disabled="state.isRecovering">
          Som de Erro
        </button>
        <button @click="testDifferentWaveforms" class="btn btn-test" :disabled="state.isRecovering">
          Testar Formas de Onda
        </button>
      </div>
    </div>

    <!-- Queue Details -->
    <div v-if="hasItemsInQueue" class="queue-details">
      <h4>📋 Itens na Fila</h4>
      <ul class="queue-list">
        <li 
          v-for="(item, index) in queueInfo.items" 
          :key="item.id"
          class="queue-item"
        >
          <span class="item-index">{{ index + 1 }}.</span>
          <span class="item-id">{{ item.id.slice(-8) }}</span>
          <span class="item-source">{{ item.source }}</span>
          <span class="item-time">{{ formatTime(item.timestamp) }}</span>
          <span v-if="item.metadata?.retryCount" class="retry-count">
            Tentativa: {{ item.metadata.retryCount }}
          </span>
          <button 
            @click="removeFromQueue(item.id)" 
            class="btn btn-small btn-danger"
          >
            ✕
          </button>
        </li>
      </ul>
    </div>

    <!-- Debug Info -->
    <div class="debug-info">
      <details>
        <summary>🔍 Debug Info</summary>
        <div class="debug-content">
          <h5>Estado do Sistema:</h5>
          <pre>{{ JSON.stringify({
            isPlaying: state.isPlaying,
            queueLength: state.queueLength,
            volume: state.volume,
            isMuted: state.isMuted,
            errorCount: state.errorCount,
            isRecovering: state.isRecovering,
            isHealthy: isHealthy
          }, null, 2) }}</pre>
          
          <h5>Relatório de Erros:</h5>
          <pre>{{ JSON.stringify(errorReport, null, 2) }}</pre>
          
          <h5>Informações da Fila:</h5>
          <pre>{{ JSON.stringify(queueInfo, null, 2) }}</pre>
        </div>
      </details>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { useAudioPlayback } from '@/composables/useAudioPlayback'
import { 
  generateTestWAV, 
  generateSuccessSound, 
  generateErrorSound,
  getAudioMetadata,
  validateAudioData
} from '@/utils/audioUtils'

const {
  state,
  enqueueAudio,
  clearQueue,
  removeFromQueue,
  stopPlayback,
  pauseQueue,
  resumeQueue,
  setVolume,
  toggleMute,
  clearErrors,
  recoverFromErrors,
  getErrorReport,
  hasItemsInQueue,
  hasErrors,
  isHealthy,
  getQueueInfo,
  cleanup
} = useAudioPlayback()

const queueInfo = computed(() => getQueueInfo())
const errorReport = computed(() => getErrorReport())

// Status text computation
const getStatusText = (): string => {
  if (state.isRecovering) return 'Recuperando'
  if (hasErrors.value) return 'Com Problemas'
  if (state.isPlaying) return 'Reproduzindo'
  return 'Parado'
}

// Error type translation
const getErrorTypeText = (type: string): string => {
  const translations = {
    'DECODE_ERROR': 'Erro de Decodificação',
    'CONTEXT_ERROR': 'Erro de Contexto',
    'PLAYBACK_ERROR': 'Erro de Reprodução',
    'QUEUE_ERROR': 'Erro de Fila',
    'UNKNOWN_ERROR': 'Erro Desconhecido'
  }
  return translations[type as keyof typeof translations] || type
}

// Event handlers
const handleVolumeChange = (event: Event) => {
  const target = event.target as HTMLInputElement
  setVolume(parseFloat(target.value))
}

// Enhanced test audio generation using WAV utilities
const generateTestAudio = () => {
  try {
    console.log('🎵 Generating test WAV audio...')
    
    const audioBuffer = generateTestWAV({
      frequency: 440, // A note
      duration: 1.0,
      amplitude: 0.1,
      waveType: 'sine'
    })
    
    // Validate the generated audio
    if (!validateAudioData(audioBuffer)) {
      throw new Error('Generated audio data is invalid')
    }
    
    const metadata = getAudioMetadata(audioBuffer)
    console.log('🎵 Generated audio metadata:', metadata)
    
    enqueueAudio(audioBuffer, {
      type: 'test',
      source: 'generator',
      ...metadata
    })
    
  } catch (error) {
    console.error('❌ Failed to generate test audio:', error)
  }
}

const simulateMultipleAudios = () => {
  try {
    console.log('🎵 Generating multiple test audios...')
    
    const frequencies = [440, 523, 659, 784] // A, C, E, G
    frequencies.forEach((freq, index) => {
      setTimeout(() => {
        const audioBuffer = generateTestWAV({
          frequency: freq,
          duration: 0.5,
          amplitude: 0.08,
          waveType: 'sine'
        })
        
        enqueueAudio(audioBuffer, {
          type: 'test-sequence',
          source: 'generator',
          frequency: freq,
          sequenceIndex: index
        })
      }, index * 100)
    })
    
  } catch (error) {
    console.error('❌ Failed to generate multiple audios:', error)
  }
}

const playSuccessSound = () => {
  try {
    console.log('🎵 Playing success sound...')
    
    const successSounds = generateSuccessSound()
    successSounds.forEach((audioBuffer, index) => {
      setTimeout(() => {
        enqueueAudio(audioBuffer, {
          type: 'success',
          source: 'generator',
          sequenceIndex: index
        })
      }, index * 50)
    })
    
  } catch (error) {
    console.error('❌ Failed to play success sound:', error)
  }
}

const playErrorSound = () => {
  try {
    console.log('🎵 Playing error sound...')
    
    const errorSounds = generateErrorSound()
    errorSounds.forEach((audioBuffer, index) => {
      setTimeout(() => {
        enqueueAudio(audioBuffer, {
          type: 'error',
          source: 'generator',
          sequenceIndex: index
        })
      }, index * 100)
    })
    
  } catch (error) {
    console.error('❌ Failed to play error sound:', error)
  }
}

const testDifferentWaveforms = () => {
  try {
    console.log('🎵 Testing different waveforms...')
    
    const waveforms: Array<'sine' | 'square' | 'sawtooth' | 'noise'> = ['sine', 'square', 'sawtooth', 'noise']
    
    waveforms.forEach((waveType, index) => {
      setTimeout(() => {
        const audioBuffer = generateTestWAV({
          frequency: 440,
          duration: 0.8,
          amplitude: 0.06,
          waveType
        })
        
        enqueueAudio(audioBuffer, {
          type: 'waveform-test',
          source: 'generator',
          waveType
        })
      }, index * 200)
    })
    
  } catch (error) {
    console.error('❌ Failed to test waveforms:', error)
  }
}

// Utility functions
const formatTime = (timestamp: number): string => {
  return new Date(timestamp).toLocaleTimeString()
}

// Lifecycle
onMounted(() => {
  console.log('🎵 AudioPlaybackControls mounted')
})

onUnmounted(() => {
  cleanup()
})
</script>

<style scoped>
.audio-playback-controls {
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 8px;
  padding: 20px;
  margin: 20px 0;
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}

.controls-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 10px;
  border-bottom: 1px solid #dee2e6;
}

.controls-header h3 {
  margin: 0;
  color: #495057;
}

.status-indicator {
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: bold;
  background: #6c757d;
  color: white;
  transition: all 0.3s ease;
}

.status-indicator.active {
  background: #28a745;
  animation: pulse 2s infinite;
}

.status-indicator.error {
  background: #dc3545;
  animation: blink 1s infinite;
}

.status-indicator.recovering {
  background: #ffc107;
  color: #000;
  animation: spin 2s linear infinite;
}

@keyframes pulse {
  0% { opacity: 1; }
  50% { opacity: 0.7; }
  100% { opacity: 1; }
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0.5; }
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

/* Error Section */
.error-section {
  background: #f8d7da;
  border: 1px solid #f5c6cb;
  border-radius: 6px;
  padding: 15px;
  margin-bottom: 20px;
}

.error-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.error-header h4 {
  margin: 0;
  color: #721c24;
}

.error-stats {
  font-size: 12px;
  color: #856404;
  background: #fff3cd;
  padding: 2px 8px;
  border-radius: 4px;
}

.error-details {
  background: white;
  border-radius: 4px;
  padding: 10px;
  margin-bottom: 10px;
  font-size: 12px;
}

.error-type {
  font-weight: bold;
  color: #dc3545;
  margin-bottom: 5px;
}

.error-message {
  color: #495057;
  margin-bottom: 5px;
}

.error-time {
  color: #6c757d;
  font-size: 11px;
}

.error-actions {
  display: flex;
  gap: 10px;
  margin-bottom: 10px;
}

.recommendations {
  background: #d1ecf1;
  border: 1px solid #bee5eb;
  border-radius: 4px;
  padding: 10px;
}

.recommendations h5 {
  margin: 0 0 5px 0;
  color: #0c5460;
}

.recommendations ul {
  margin: 0;
  padding-left: 20px;
  font-size: 12px;
  color: #0c5460;
}

.queue-status {
  margin-bottom: 20px;
}

.queue-info {
  display: flex;
  gap: 20px;
  margin-bottom: 10px;
  font-size: 14px;
  color: #6c757d;
  flex-wrap: wrap;
  align-items: center;
}

.queue-count {
  font-weight: bold;
}

.current-playing {
  color: #28a745;
  font-weight: bold;
}

.recovering-indicator {
  color: #ffc107;
  font-weight: bold;
  animation: pulse 1.5s infinite;
}

.queue-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.volume-controls {
  margin-bottom: 20px;
  padding: 15px;
  background: white;
  border-radius: 6px;
  border: 1px solid #e9ecef;
}

.volume-controls label {
  display: block;
  margin-bottom: 8px;
  font-weight: bold;
  color: #495057;
}

.volume-group {
  display: flex;
  align-items: center;
  gap: 10px;
}

.volume-slider {
  flex: 1;
  height: 6px;
  background: #dee2e6;
  outline: none;
  border-radius: 3px;
}

.volume-slider::-webkit-slider-thumb {
  appearance: none;
  width: 18px;
  height: 18px;
  background: #007bff;
  border-radius: 50%;
  cursor: pointer;
}

.volume-display {
  min-width: 40px;
  text-align: center;
  font-weight: bold;
  color: #495057;
}

.test-section {
  margin-bottom: 20px;
  padding: 15px;
  background: #e3f2fd;
  border-radius: 6px;
  border: 1px solid #bbdefb;
}

.test-section h4 {
  margin: 0 0 10px 0;
  color: #1976d2;
}

.test-controls {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.queue-details {
  margin-bottom: 20px;
}

.queue-details h4 {
  margin: 0 0 10px 0;
  color: #495057;
}

.queue-list {
  list-style: none;
  padding: 0;
  margin: 0;
  max-height: 200px;
  overflow-y: auto;
  border: 1px solid #dee2e6;
  border-radius: 4px;
}

.queue-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-bottom: 1px solid #f8f9fa;
  font-size: 12px;
}

.queue-item:last-child {
  border-bottom: none;
}

.item-index {
  font-weight: bold;
  color: #6c757d;
  min-width: 20px;
}

.item-id {
  font-family: monospace;
  background: #f8f9fa;
  padding: 2px 4px;
  border-radius: 2px;
  flex: 1;
}

.item-source {
  background: #e9ecef;
  padding: 1px 4px;
  border-radius: 2px;
  font-size: 11px;
  color: #495057;
}

.item-time {
  color: #6c757d;
  font-size: 11px;
}

.retry-count {
  background: #fff3cd;
  color: #856404;
  padding: 1px 4px;
  border-radius: 2px;
  font-size: 10px;
}

.debug-info {
  margin-top: 20px;
}

.debug-info details {
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 4px;
  padding: 10px;
}

.debug-content h5 {
  margin: 10px 0 5px 0;
  color: #495057;
}

.debug-info pre {
  margin: 5px 0 10px 0;
  font-size: 11px;
  line-height: 1.4;
  max-height: 150px;
  overflow: auto;
  background: white;
  padding: 8px;
  border-radius: 4px;
}

/* Button Styles */
.btn {
  padding: 6px 12px;
  border: 1px solid transparent;
  border-radius: 4px;
  font-size: 12px;
  font-weight: bold;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s ease;
  text-decoration: none;
  display: inline-block;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  background: #007bff;
  color: white;
  border-color: #007bff;
}

.btn-primary:hover:not(:disabled) {
  background: #0056b3;
}

.btn-secondary {
  background: #6c757d;
  color: white;
  border-color: #6c757d;
}

.btn-secondary:hover:not(:disabled) {
  background: #545b62;
}

.btn-danger {
  background: #dc3545;
  color: white;
  border-color: #dc3545;
}

.btn-danger:hover:not(:disabled) {
  background: #bd2130;
}

.btn-warning {
  background: #ffc107;
  color: #000;
  border-color: #ffc107;
}

.btn-warning:hover:not(:disabled) {
  background: #e0a800;
}

.btn-success {
  background: #28a745;
  color: white;
  border-color: #28a745;
}

.btn-success:hover:not(:disabled) {
  background: #1e7e34;
}

.btn-test {
  background: #17a2b8;
  color: white;
  border-color: #17a2b8;
}

.btn-test:hover:not(:disabled) {
  background: #117a8b;
}

.btn-mute {
  background: transparent;
  border: 1px solid #dee2e6;
  font-size: 16px;
  padding: 4px 8px;
}

.btn-mute.muted {
  background: #dc3545;
  color: white;
  border-color: #dc3545;
}

.btn-small {
  padding: 2px 6px;
  font-size: 10px;
}
</style> 