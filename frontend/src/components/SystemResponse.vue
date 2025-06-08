<template>
  <section class="system-response">
    <header class="response-header">
      <h2 class="section-title">
        <span class="section-icon">🤖</span>
        Resposta do Sistema
      </h2>
      <div class="response-controls">
        <button 
          v-if="response" 
          class="copy-button"
          @click="handleCopy"
          title="Copiar resposta"
        >
          📋
        </button>
        <button 
          v-if="response" 
          class="clear-button"
          @click="handleClear"
          :disabled="isPlaying"
          title="Limpar resposta"
        >
          🗑️
        </button>
      </div>
    </header>

    <div 
      class="response-container" 
      :class="{ 
        'playing': isPlaying,
        'empty': !response,
        'has-content': !!response,
        'loading': isProcessing
      }"
    >
      <!-- Indicador de reprodução -->
      <div v-if="isPlaying" class="playing-indicator">
        <div class="audio-wave">
          <div class="wave-bar"></div>
          <div class="wave-bar"></div>
          <div class="wave-bar"></div>
        </div>
        <span class="playing-text">Reproduzindo...</span>
      </div>

      <!-- Indicador de processamento -->
      <div v-if="isProcessing" class="processing-indicator">
        <div class="processing-spinner"></div>
        <span class="processing-text">Processando resposta...</span>
      </div>

      <!-- Conteúdo da resposta -->
      <div class="response-content" ref="contentRef">
        <div v-if="!response && !isProcessing" class="placeholder">
          <span class="placeholder-icon">🎧</span>
          <span class="placeholder-text">{{ placeholderText }}</span>
        </div>
        
        <div v-else-if="response" class="response-text">
          <div class="response-body">
            {{ responseText }}
          </div>
          
          <!-- Metadados da resposta -->
          <div v-if="showMetadata && responseMetadata" class="response-metadata">
            <div v-if="responseMetadata.timestamp" class="metadata-item">
              <span class="metadata-label">Recebido:</span>
              <span class="metadata-value">{{ formatTime(responseMetadata.timestamp) }}</span>
            </div>
            <div v-if="responseMetadata.source" class="metadata-item">
              <span class="metadata-label">Fonte:</span>
              <span class="metadata-value">{{ responseMetadata.source }}</span>
            </div>
            <div v-if="responseMetadata.duration" class="metadata-item">
              <span class="metadata-label">Duração:</span>
              <span class="metadata-value">{{ formatDuration(responseMetadata.duration) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Estatísticas da resposta -->
      <div v-if="response && showStats" class="response-stats">
        <span class="stat">
          <span class="stat-label">Palavras:</span>
          <span class="stat-value">{{ wordCount }}</span>
        </span>
        <span class="stat">
          <span class="stat-label">Caracteres:</span>
          <span class="stat-value">{{ charCount }}</span>
        </span>
        <span v-if="responseTime" class="stat">
          <span class="stat-label">Tempo de resposta:</span>
          <span class="stat-value">{{ responseTime }}ms</span>
        </span>
      </div>
    </div>

    <!-- Feedback de ação -->
    <Transition name="fade">
      <div v-if="feedbackMessage" class="feedback-message" :class="feedbackType">
        {{ feedbackMessage }}
      </div>
    </Transition>
  </section>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'

interface ResponseMetadata {
  timestamp?: number
  source?: string
  duration?: number
  confidence?: number
}

interface Props {
  response?: string | Blob
  isPlaying?: boolean
  isProcessing?: boolean
  placeholder?: string
  showStats?: boolean
  showMetadata?: boolean
  responseMetadata?: ResponseMetadata
  responseTime?: number
  autoScroll?: boolean
  maxHeight?: string
}

interface Emits {
  (e: 'clear'): void
  (e: 'copy', text: string): void
  (e: 'replay'): void
}

const props = withDefaults(defineProps<Props>(), {
  response: '',
  isPlaying: false,
  isProcessing: false,
  placeholder: 'Aguardando resposta do sistema...',
  showStats: true,
  showMetadata: false,
  autoScroll: true,
  maxHeight: '200px'
})

const emit = defineEmits<Emits>()

// Refs
const contentRef = ref<HTMLDivElement | null>(null)
const feedbackMessage = ref('')
const feedbackType = ref<'success' | 'error'>('success')

// Computed properties
const placeholderText = computed(() => {
  if (props.isProcessing) return 'Processando...'
  if (props.isPlaying) return 'Reproduzindo resposta...'
  return props.placeholder
})

const responseText = computed(() => {
  if (!props.response) return ''
  if (typeof props.response === 'string') return props.response
  if (props.response instanceof Blob) return '[Dados de áudio recebidos]'
  return String(props.response)
})

const wordCount = computed(() => {
  const text = responseText.value
  if (!text) return 0
  return text.trim().split(/\s+/).filter(word => word.length > 0).length
})

const charCount = computed(() => {
  return responseText.value.length
})

// Métodos
const handleClear = (): void => {
  emit('clear')
  showFeedback('Resposta limpa', 'success')
}

const handleCopy = async (): Promise<void> => {
  try {
    const textToCopy = responseText.value
    await navigator.clipboard.writeText(textToCopy)
    emit('copy', textToCopy)
    showFeedback('Resposta copiada!', 'success')
  } catch (error) {
    console.error('Erro ao copiar resposta:', error)
    showFeedback('Erro ao copiar resposta', 'error')
  }
}

const showFeedback = (message: string, type: 'success' | 'error'): void => {
  feedbackMessage.value = message
  feedbackType.value = type
  
  setTimeout(() => {
    feedbackMessage.value = ''
  }, 2000)
}

const formatTime = (timestamp: number): string => {
  const now = Date.now()
  const diff = now - timestamp
  
  if (diff < 1000) return 'agora'
  if (diff < 60000) return `${Math.floor(diff / 1000)}s atrás`
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m atrás`
  
  return new Date(timestamp).toLocaleTimeString('pt-BR', {
    hour: '2-digit',
    minute: '2-digit'
  })
}

const formatDuration = (durationMs: number): string => {
  const seconds = Math.floor(durationMs / 1000)
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  
  if (minutes > 0) {
    return `${minutes}m ${remainingSeconds}s`
  }
  return `${remainingSeconds}s`
}

const scrollToBottom = async (): Promise<void> => {
  if (!props.autoScroll || !contentRef.value) return
  
  await nextTick()
  contentRef.value.scrollTop = contentRef.value.scrollHeight
}

// Watch para mudanças na resposta
watch(() => responseText.value, (newResponse) => {
  if (newResponse) {
    scrollToBottom()
  }
}, { immediate: true })

// Watch para estado de reprodução
watch(() => props.isPlaying, (playing) => {
  if (playing) {
    scrollToBottom()
  }
})
</script>

<style scoped>
.system-response {
  background: rgba(31, 41, 55, 0.6);
  border: 1px solid #4b5563;
  border-radius: 16px;
  padding: clamp(1rem, 3vw, 1.5rem);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  backdrop-filter: blur(10px);
  display: flex;
  flex-direction: column;
}

.response-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  gap: 1rem;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0;
  font-size: clamp(1.1rem, 3.5vw, 1.2rem);
  font-weight: 600;
  color: #9ca3af;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.section-icon {
  font-size: clamp(1.2rem, 3.5vw, 1.3rem);
  color: #818cf8;
}

.response-controls button {
  padding: 0.5rem;
  border: 1px solid #4b5563;
  background: #374151;
  color: #d1d5db;
  border-radius: 6px;
  cursor: pointer;
  font-size: 1rem;
  transition: all 0.2s ease;
  line-height: 1;
}
.response-controls button:hover:not(:disabled) {
  background: #4f46e5;
  border-color: #6366f1;
  color: white;
}
.response-controls button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.response-container {
  position: relative;
  flex: 1;
  min-height: 150px;
  padding: 1rem;
  border-radius: 12px;
  background: #1f2937;
  border: 1px solid #4b5563;
  transition: all 0.3s ease;
  overflow-y: auto;
  font-family: 'Inter', system-ui, sans-serif;
  display: flex;
  align-items: center;
  justify-content: center;
}

.response-container.playing {
  border-color: #10b981;
  box-shadow: 0 0 20px rgba(16, 185, 129, 0.3);
}

.response-container.loading {
  border-color: #f59e0b;
  box-shadow: 0 0 20px rgba(245, 158, 11, 0.3);
}

.response-container.has-content {
  align-items: flex-start;
  justify-content: flex-start;
}

.playing-indicator {
  position: absolute;
  top: 0.75rem;
  right: 0.75rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: #10b981;
  font-size: 0.9rem;
  font-weight: 600;
  z-index: 1;
}

.audio-wave {
  display: flex;
  gap: 2px;
}

.wave-bar {
  width: 3px;
  height: 12px;
  background: #10b981;
  border-radius: 2px;
  animation: wave 1.5s infinite ease-in-out;
}

.wave-bar:nth-child(2) {
  animation-delay: 0.2s;
}

.wave-bar:nth-child(3) {
  animation-delay: 0.4s;
}

.playing-text {
  background: rgba(255, 255, 255, 0.9);
  padding: 0.25rem 0.5rem;
  border-radius: 6px;
  font-size: 0.8rem;
}

.processing-indicator {
  position: absolute;
  top: 0.75rem;
  right: 0.75rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: #f59e0b;
  font-size: 0.9rem;
  font-weight: 600;
  z-index: 1;
}

.processing-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid #fed7aa;
  border-top: 2px solid #f59e0b;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.processing-text {
  background: rgba(255, 255, 255, 0.9);
  padding: 0.25rem 0.5rem;
  border-radius: 6px;
  font-size: 0.8rem;
}

.response-content {
  width: 100%;
}

.placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  color: #6b7280;
}

.placeholder-icon {
  font-size: 2.5rem;
  opacity: 0.6;
}

.placeholder-text {
  font-size: 1rem;
  font-weight: 500;
  text-align: center;
  opacity: 0.8;
}

.response-text {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.response-body {
  font-size: 1.1rem;
  line-height: 1.6;
  color: #374151;
  word-wrap: break-word;
  white-space: pre-wrap;
}

.response-metadata {
  padding: 1rem;
  background: #f1f5f9;
  border-radius: 8px;
  border-left: 4px solid #10b981;
  font-size: 0.9rem;
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
}

.metadata-item {
  display: flex;
  gap: 0.25rem;
}

.metadata-label {
  color: #6b7280;
  font-weight: 500;
}

.metadata-value {
  color: #374151;
  font-weight: 600;
}

.response-stats {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid #e2e8f0;
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  font-size: 0.9rem;
}

.stat {
  display: flex;
  gap: 0.25rem;
}

.stat-label {
  color: #6b7280;
  font-weight: 500;
}

.stat-value {
  color: #374151;
  font-weight: 600;
}

.feedback-message {
  position: absolute;
  bottom: -2.5rem;
  left: 50%;
  transform: translateX(-50%);
  padding: 0.5rem 1rem;
  border-radius: 8px;
  font-size: 0.9rem;
  font-weight: 500;
  white-space: nowrap;
  z-index: 10;
}

.feedback-message.success {
  background: #10b981;
  color: white;
}

.feedback-message.error {
  background: #ef4444;
  color: white;
}

/* Animações */
@keyframes wave {
  0%, 100% { 
    transform: scaleY(1); 
  }
  25% { 
    transform: scaleY(0.3); 
  }
  50% { 
    transform: scaleY(0.7); 
  }
  75% { 
    transform: scaleY(0.5); 
  }
}

@keyframes spin {
  to { 
    transform: rotate(360deg); 
  }
}

/* Transições */
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from, .fade-leave-to {
  opacity: 0;
}

/* Scrollbar customizada */
.response-container::-webkit-scrollbar {
  width: 6px;
}

.response-container::-webkit-scrollbar-track {
  background: #f1f5f9;
  border-radius: 3px;
}

.response-container::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 3px;
}

.response-container::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}

/* Responsividade */
@media (max-width: 640px) {
  .system-response {
    padding: 1rem;
  }
  
  .section-title {
    font-size: 1.1rem;
  }
  
  .response-container {
    min-height: 80px;
    padding: 1rem;
  }
  
  .response-stats,
  .response-metadata {
    flex-direction: column;
    gap: 0.5rem;
  }
  
  .placeholder-icon {
    font-size: 2rem;
  }
  
  .placeholder-text {
    font-size: 0.9rem;
  }
}
</style> 