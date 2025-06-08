<template>
  <section class="transcription-display">
    <header class="transcription-header">
      <h2 class="section-title">
        <span class="section-icon">📝</span>
        Transcrição
      </h2>
      <div class="transcription-controls">
        <button 
          v-if="transcription" 
          class="clear-button"
          @click="handleClear"
          :disabled="isRecording"
          title="Limpar transcrição"
        >
          🗑️
        </button>
        <button 
          v-if="transcription" 
          class="copy-button"
          @click="handleCopy"
          title="Copiar transcrição"
        >
          📋
        </button>
      </div>
    </header>

    <div 
      class="transcription-container" 
      :class="{ 
        'active': isRecording,
        'empty': !transcription,
        'has-content': !!transcription
      }"
    >
      <!-- Indicador de gravação -->
      <div v-if="isRecording" class="recording-indicator">
        <div class="pulse"></div>
        <span class="recording-text">Gravando...</span>
      </div>

      <!-- Conteúdo da transcrição -->
      <div class="transcription-content" ref="contentRef">
        <div v-if="!transcription && !isRecording" class="placeholder">
          <span class="placeholder-icon">🎤</span>
          <span class="placeholder-text">{{ placeholderText }}</span>
        </div>
        
        <div v-else-if="transcription" class="transcription-text">
          {{ transcription }}
          <span v-if="isRecording" class="typing-cursor">|</span>
        </div>
        
        <div v-else-if="isRecording" class="listening-indicator">
          <span class="listening-text">Aguardando sua voz...</span>
          <div class="sound-waves">
            <div class="wave"></div>
            <div class="wave"></div>
            <div class="wave"></div>
          </div>
        </div>
      </div>

      <!-- Estatísticas da transcrição -->
      <div v-if="transcription && showStats" class="transcription-stats">
        <span class="stat">
          <span class="stat-label">Palavras:</span>
          <span class="stat-value">{{ wordCount }}</span>
        </span>
        <span class="stat">
          <span class="stat-label">Caracteres:</span>
          <span class="stat-value">{{ charCount }}</span>
        </span>
        <span v-if="lastUpdated" class="stat">
          <span class="stat-label">Última atualização:</span>
          <span class="stat-value">{{ formatTime(lastUpdated) }}</span>
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

interface Props {
  transcription?: string
  isRecording?: boolean
  placeholder?: string
  showStats?: boolean
  autoScroll?: boolean
  maxHeight?: string
}

interface Emits {
  (e: 'clear'): void
  (e: 'copy', text: string): void
}

const props = withDefaults(defineProps<Props>(), {
  transcription: '',
  isRecording: false,
  placeholder: 'Clique no botão do microfone para começar...',
  showStats: true,
  autoScroll: true,
  maxHeight: '200px'
})

const emit = defineEmits<Emits>()

// Refs
const contentRef = ref<HTMLDivElement | null>(null)
const feedbackMessage = ref('')
const feedbackType = ref<'success' | 'error'>('success')
const lastUpdated = ref<number | null>(null)

// Computed properties
const placeholderText = computed(() => {
  if (props.isRecording) return 'Escutando...'
  return props.placeholder
})

const wordCount = computed(() => {
  if (!props.transcription) return 0
  return props.transcription.trim().split(/\s+/).filter(word => word.length > 0).length
})

const charCount = computed(() => {
  return props.transcription.length
})

// Métodos
const handleClear = (): void => {
  emit('clear')
  showFeedback('Transcrição limpa', 'success')
}

const handleCopy = async (): Promise<void> => {
  try {
    await navigator.clipboard.writeText(props.transcription)
    emit('copy', props.transcription)
    showFeedback('Texto copiado!', 'success')
  } catch (error) {
    console.error('Erro ao copiar texto:', error)
    showFeedback('Erro ao copiar texto', 'error')
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

const scrollToBottom = async (): Promise<void> => {
  if (!props.autoScroll || !contentRef.value) return
  
  await nextTick()
  contentRef.value.scrollTop = contentRef.value.scrollHeight
}

// Watch para mudanças na transcrição
watch(() => props.transcription, (newTranscription) => {
  if (newTranscription) {
    lastUpdated.value = Date.now()
    scrollToBottom()
  }
}, { immediate: true })

// Watch para estado de gravação
watch(() => props.isRecording, (recording) => {
  if (recording) {
    lastUpdated.value = Date.now()
  }
})
</script>

<style scoped>
.transcription-display {
  background: rgba(31, 41, 55, 0.6);
  border: 1px solid #4b5563;
  border-radius: 16px;
  padding: clamp(1rem, 3vw, 1.5rem);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  backdrop-filter: blur(10px);
  display: flex;
  flex-direction: column;
}

.transcription-header {
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

.transcription-controls button {
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
.transcription-controls button:hover:not(:disabled) {
  background: #4f46e5;
  border-color: #6366f1;
  color: white;
}
.transcription-controls button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.transcription-container {
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
}

.transcription-container.active {
  border-color: #6366f1;
  box-shadow: 0 0 20px rgba(99, 102, 241, 0.3);
}

.transcription-container.empty {
  display: flex;
  align-items: center;
  justify-content: center;
  border-style: dashed;
  border-color: #cbd5e1;
}

.transcription-container.has-content {
  align-items: stretch;
}

.transcription-content {
  color: #d1d5db;
  font-size: clamp(0.9rem, 2.5vw, 1.05rem);
  line-height: 1.7;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: clamp(0.5rem, 2vw, 1rem);
  color: #6b7280;
  text-align: center;
  padding: clamp(1rem, 4vw, 2rem);
}

.empty-icon {
  font-size: clamp(2rem, 8vw, 2.5rem);
  opacity: 0.6;
  animation: float 3s ease-in-out infinite;
}

.empty-text {
  font-size: clamp(0.85rem, 2.5vw, 0.95rem);
  opacity: 0.8;
}

.recording-indicator {
  position: absolute;
  top: clamp(0.4rem, 1vw, 0.5rem);
  right: clamp(0.4rem, 1vw, 0.5rem);
  display: flex;
  align-items: center;
  gap: clamp(0.25rem, 1vw, 0.5rem);
  color: #dc2626;
  font-size: clamp(0.8rem, 2vw, 0.9rem);
  font-weight: 600;
  background: rgba(255, 255, 255, 0.9);
  padding: clamp(0.25rem, 1vw, 0.5rem) clamp(0.5rem, 1.5vw, 0.75rem);
  border-radius: 50px;
  backdrop-filter: blur(4px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.pulse {
  width: clamp(6px, 1.5vw, 8px);
  height: clamp(6px, 1.5vw, 8px);
  background: #dc2626;
  border-radius: 50%;
  animation: pulse 1s infinite;
  flex-shrink: 0;
}

.recording-text {
  background: rgba(255, 255, 255, 0.9);
  padding: 0.25rem 0.5rem;
  border-radius: 6px;
  font-size: 0.8rem;
}

.typing-cursor {
  display: inline-block;
  width: 2px;
  height: 1.2em;
  background: #4f46e5;
  margin-left: 2px;
  animation: blink 1s infinite;
}

.listening-indicator {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
  color: #6b7280;
}

.listening-text {
  font-size: 1rem;
  font-weight: 500;
}

.sound-waves {
  display: flex;
  gap: 4px;
  align-items: end;
}

.wave {
  width: 4px;
  height: 20px;
  background: #4f46e5;
  border-radius: 2px;
  animation: wave 1.5s infinite ease-in-out;
}

.wave:nth-child(2) {
  animation-delay: 0.3s;
}

.wave:nth-child(3) {
  animation-delay: 0.6s;
}

.transcription-stats {
  margin-top: clamp(0.5rem, 2vw, 1rem);
  padding-top: clamp(0.5rem, 2vw, 1rem);
  border-top: 1px solid #e2e8f0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: clamp(0.5rem, 2vw, 1rem);
  font-size: clamp(0.75rem, 2vw, 0.85rem);
  color: #6b7280;
  flex-wrap: wrap;
}

.stats-item {
  display: flex;
  align-items: center;
  gap: clamp(0.25rem, 1vw, 0.5rem);
  white-space: nowrap;
}

.stats-icon {
  font-size: clamp(0.8rem, 2vw, 0.9rem);
  opacity: 0.7;
}

.feedback-message {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background: rgba(0, 0, 0, 0.8);
  color: white;
  padding: clamp(0.5rem, 2vw, 0.75rem) clamp(0.75rem, 3vw, 1rem);
  border-radius: 8px;
  font-size: clamp(0.8rem, 2.5vw, 0.9rem);
  font-weight: 500;
  z-index: 10;
  backdrop-filter: blur(4px);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
}

.feedback-message.success {
  background: rgba(16, 185, 129, 0.9);
}

.feedback-message.error {
  background: rgba(239, 68, 68, 0.9);
}

/* Animações */
@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.3; transform: scale(0.8); }
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

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

@keyframes float {
  0%, 100% { transform: translateY(0px); }
  50% { transform: translateY(-8px); }
}

/* Transições */
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from, .fade-leave-to {
  opacity: 0;
}

/* Scrollbar personalizada */
.transcription-container::-webkit-scrollbar {
  width: clamp(4px, 1vw, 6px);
}

.transcription-container::-webkit-scrollbar-track {
  background: #f1f5f9;
  border-radius: 3px;
}

.transcription-container::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 3px;
}

.transcription-container::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}

/* Responsive Design */

/* Mobile - Retrato */
@media (max-width: 480px) {
  .transcription-header {
    flex-direction: column;
    align-items: stretch;
    gap: 0.75rem;
  }
  
  .section-title {
    justify-content: center;
  }
  
  .transcription-controls {
    justify-content: center;
  }
  
  .transcription-stats {
    flex-direction: column;
    gap: 0.5rem;
    text-align: center;
  }
  
  .recording-indicator {
    position: static;
    align-self: center;
    margin-bottom: 0.5rem;
  }
}

/* Tablet */
@media (min-width: 768px) {
  .transcription-container {
    min-height: 120px;
    max-height: 250px;
  }
}

/* Desktop */
@media (min-width: 1024px) {
  .transcription-container {
    min-height: 140px;
    max-height: 300px;
  }
}

/* Modo escuro */
@media (prefers-color-scheme: dark) {
  .transcription-display {
    background: rgba(31, 41, 55, 0.95);
  }
  
  .section-title {
    color: #a5b4fc;
  }
  
  .clear-button,
  .copy-button {
    background: #374151;
    color: #d1d5db;
  }
  
  .clear-button:hover:not(:disabled) {
    background: #ef4444;
  }
  
  .copy-button:hover {
    background: #6366f1;
  }
  
  .transcription-container {
    background: #1f2937;
    border-color: #374151;
    color: #f9fafb;
  }
  
  .transcription-container.active {
    border-color: #6366f1;
    background: #312e81;
  }
  
  .transcription-stats {
    border-color: #374151;
    color: #9ca3af;
  }
  
  .empty-state {
    color: #9ca3af;
  }
  
  .recording-indicator {
    background: rgba(31, 41, 55, 0.9);
    color: #fca5a5;
  }
}

/* Acessibilidade - movimento reduzido */
@media (prefers-reduced-motion: reduce) {
  .pulse,
  .empty-icon,
  .typing-cursor {
    animation: none;
  }
  
  .clear-button,
  .copy-button,
  .transcription-container {
    transition: none;
  }
}

/* Print */
@media print {
  .transcription-display {
    background: white;
    box-shadow: none;
    border: 1px solid #000;
  }
  
  .transcription-controls,
  .recording-indicator {
    display: none;
  }
  
  .section-title {
    color: #000;
  }
  
  .transcription-container {
    background: white;
    border: 1px solid #666;
    max-height: none;
    overflow: visible;
  }
  
  .transcription-content {
    color: #000;
  }
}
</style> 