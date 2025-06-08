<template>
  <div class="audio-visualizer" ref="visualizerContainer">
    <canvas 
      ref="canvas"
      :width="width"
      :height="height"
      class="visualizer-canvas"
    />
    <div v-if="!isActive && !mediaStream" class="visualizer-placeholder">
      <span class="placeholder-icon">🎵</span>
      <span class="placeholder-text">Aguardando áudio...</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, computed } from 'vue'

interface Props {
  mediaStream?: MediaStream | null
  width?: number
  height?: number
  isRecording?: boolean
  isPlaying?: boolean
  barColor?: string
  backgroundColor?: string
  sensitivity?: number
}

const props = withDefaults(defineProps<Props>(), {
  width: 400,
  height: 100,
  isRecording: false,
  isPlaying: false,
  barColor: '#4f46e5',
  backgroundColor: 'transparent',
  sensitivity: 1.0
})

// Refs
const canvas = ref<HTMLCanvasElement | null>(null)
const visualizerContainer = ref<HTMLDivElement | null>(null)
const animationId = ref<number | null>(null)

// Audio context e analyzer
const audioContext = ref<AudioContext | null>(null)
const analyser = ref<AnalyserNode | null>(null)
const dataArray = ref<Uint8Array | null>(null)
const source = ref<MediaStreamAudioSourceNode | null>(null)

// Estado
const isActive = computed(() => props.isRecording || props.isPlaying)

/**
 * Inicializa o contexto de áudio e analisador
 */
const initAudioContext = async (): Promise<void> => {
  try {
    if (!props.mediaStream) return

    // Criar contexto de áudio
    audioContext.value = new AudioContext()
    
    // Criar analisador
    analyser.value = audioContext.value.createAnalyser()
    analyser.value.fftSize = 256
    
    const bufferLength = analyser.value.frequencyBinCount
    dataArray.value = new Uint8Array(bufferLength)
    
    // Criar source do media stream
    source.value = audioContext.value.createMediaStreamSource(props.mediaStream)
    source.value.connect(analyser.value)
    
    console.log('✅ AudioVisualizer: Contexto de áudio inicializado')
  } catch (error) {
    console.error('❌ AudioVisualizer: Erro ao inicializar contexto de áudio:', error)
  }
}

/**
 * Desenha a visualização de áudio no canvas
 */
const draw = (): void => {
  if (!canvas.value || !analyser.value || !dataArray.value) {
    requestAnimationFrame(draw)
    return
  }

  const canvasContext = canvas.value.getContext('2d')
  if (!canvasContext) return

  // Obter dados de frequência
  analyser.value.getByteFrequencyData(dataArray.value)

  // Limpar canvas
  canvasContext.fillStyle = props.backgroundColor
  canvasContext.fillRect(0, 0, props.width, props.height)

  // Configurar desenho das barras
  const barWidth = (props.width / dataArray.value.length) * 2.5
  let barHeight: number
  let x = 0

  // Desenhar barras de frequência
  for (let i = 0; i < dataArray.value.length; i++) {
    // Aplicar sensibilidade
    barHeight = (dataArray.value[i] * props.sensitivity) / 255 * props.height

    // Criar gradiente para as barras
    const gradient = canvasContext.createLinearGradient(0, props.height - barHeight, 0, props.height)
    gradient.addColorStop(0, props.barColor)
    gradient.addColorStop(1, adjustColor(props.barColor, -0.3))

    canvasContext.fillStyle = gradient
    canvasContext.fillRect(x, props.height - barHeight, barWidth, barHeight)

    x += barWidth + 1
  }

  // Continuar animação se estiver ativo
  if (isActive.value) {
    animationId.value = requestAnimationFrame(draw)
  }
}

/**
 * Desenha visualização estática quando não há áudio
 */
const drawStatic = (): void => {
  if (!canvas.value) return

  const canvasContext = canvas.value.getContext('2d')
  if (!canvasContext) return

  // Limpar canvas
  canvasContext.fillStyle = props.backgroundColor
  canvasContext.fillRect(0, 0, props.width, props.height)

  // Desenhar barras estáticas baixas
  const barWidth = (props.width / 32) * 2.5
  let x = 0

  for (let i = 0; i < 32; i++) {
    const barHeight = Math.random() * 10 + 5 // Barras baixas aleatórias
    
    canvasContext.fillStyle = adjustColor(props.barColor, -0.6)
    canvasContext.fillRect(x, props.height - barHeight, barWidth, barHeight)

    x += barWidth + 1
  }
}

/**
 * Ajusta cor para criar gradientes
 */
const adjustColor = (color: string, factor: number): string => {
  // Converter hex para RGB
  const hex = color.replace('#', '')
  const r = parseInt(hex.substr(0, 2), 16)
  const g = parseInt(hex.substr(2, 2), 16)
  const b = parseInt(hex.substr(4, 2), 16)
  
  // Ajustar brilho
  const newR = Math.max(0, Math.min(255, r + (r * factor)))
  const newG = Math.max(0, Math.min(255, g + (g * factor)))
  const newB = Math.max(0, Math.min(255, b + (b * factor)))
  
  // Converter de volta para hex
  return `#${Math.round(newR).toString(16).padStart(2, '0')}${Math.round(newG).toString(16).padStart(2, '0')}${Math.round(newB).toString(16).padStart(2, '0')}`
}

/**
 * Inicia a visualização
 */
const startVisualization = async (): Promise<void> => {
  try {
    await initAudioContext()
    
    if (animationId.value) {
      cancelAnimationFrame(animationId.value)
    }
    
    draw()
  } catch (error) {
    console.error('❌ AudioVisualizer: Erro ao iniciar visualização:', error)
  }
}

/**
 * Para a visualização
 */
const stopVisualization = (): void => {
  if (animationId.value) {
    cancelAnimationFrame(animationId.value)
    animationId.value = null
  }
  
  // Limpar recursos de áudio
  if (source.value) {
    source.value.disconnect()
    source.value = null
  }
  
  if (audioContext.value) {
    audioContext.value.close()
    audioContext.value = null
  }
  
  analyser.value = null
  dataArray.value = null
  
  // Desenhar estado estático
  drawStatic()
}

// Watch para mudanças no mediaStream
watch(() => props.mediaStream, async (newStream) => {
  if (newStream && isActive.value) {
    await startVisualization()
  } else {
    stopVisualization()
  }
}, { immediate: true })

// Watch para estado ativo
watch(isActive, async (active) => {
  if (active && props.mediaStream) {
    await startVisualization()
  } else {
    stopVisualization()
  }
}, { immediate: true })

// Lifecycle
onMounted(() => {
  // Desenhar estado inicial
  drawStatic()
})

onUnmounted(() => {
  stopVisualization()
})

// Exposar métodos públicos se necessário
defineExpose({
  startVisualization,
  stopVisualization
})
</script>

<style scoped>
.audio-visualizer {
  position: relative;
  width: 100%;
  /* height: 100%; */
  flex-grow: 1;
  min-height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  background: #1f2937;
  border: 1px solid #4b5563;
  overflow: hidden;
  transition: all 0.3s ease;
}

.audio-visualizer.recording {
  border-color: #f43f5e;
  box-shadow: 0 0 30px rgba(244, 63, 94, 0.3);
}

.audio-visualizer.playing {
  border-color: #10b981;
  box-shadow: 0 0 30px rgba(16, 185, 129, 0.3);
}

.visualizer-canvas {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
}

.visualizer-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: clamp(0.5rem, 2vw, 1rem);
  padding: clamp(1rem, 4vw, 2rem);
  color: #9ca3af;
  text-align: center;
}

.placeholder-icon {
  font-size: clamp(2rem, 8vw, 3rem);
  opacity: 0.7;
  animation: float 3s ease-in-out infinite;
}

.placeholder-text {
  font-size: clamp(0.9rem, 3vw, 1.1rem);
  font-weight: 500;
  opacity: 0.8;
}

/* Animações */
@keyframes float {
  0%, 100% { transform: translateY(0px); }
  50% { transform: translateY(-10px); }
}

/* Responsive Design */

/* Tablet */
@media (min-width: 768px) {
  .audio-visualizer {
    min-height: 100px;
  }
}

/* Desktop */
@media (min-width: 1024px) {
  .audio-visualizer {
    min-height: 120px;
  }
}

/* Mobile - Reduzir padding */
@media (max-width: 480px) {
  .visualizer-placeholder {
    padding: clamp(0.75rem, 3vw, 1rem);
  }
  
  .placeholder-icon {
    font-size: clamp(1.5rem, 6vw, 2rem);
  }
  
  .placeholder-text {
    font-size: clamp(0.8rem, 2.5vw, 0.9rem);
  }
}

/* Modo escuro */
@media (prefers-color-scheme: dark) {
  .audio-visualizer {
    background: linear-gradient(135deg, #1f2937 0%, #374151 100%);
    border-color: #4b5563;
  }
  
  .audio-visualizer.recording {
    background: linear-gradient(135deg, #7f1d1d 0%, #991b1b 100%);
    border-color: #dc2626;
  }
  
  .audio-visualizer.playing {
    background: linear-gradient(135deg, #065f46 0%, #047857 100%);
    border-color: #10b981;
  }
  
  .visualizer-placeholder {
    color: #d1d5db;
  }
}

/* Acessibilidade - movimento reduzido */
@media (prefers-reduced-motion: reduce) {
  .placeholder-icon {
    animation: none;
  }
  
  .audio-visualizer {
    transition: none;
  }
}

/* Print */
@media print {
  .audio-visualizer {
    border: 1px solid #000;
    background: white;
  }
  
  .visualizer-placeholder {
    color: #000;
  }
}
</style> 