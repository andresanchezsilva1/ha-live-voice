import { ref, reactive, computed, readonly } from 'vue'

interface AudioQueueItem {
  id: string
  audioData: ArrayBuffer
  timestamp: number
  source?: string
  metadata?: Record<string, any>
}

interface PlaybackState {
  isPlaying: boolean
  currentItem: AudioQueueItem | null
  queueLength: number
  playbackPosition: number
  volume: number
  isMuted: boolean
  lastError: AudioError | null
  errorCount: number
  isRecovering: boolean
}

interface AudioError {
  type: 'DECODE_ERROR' | 'CONTEXT_ERROR' | 'PLAYBACK_ERROR' | 'QUEUE_ERROR' | 'UNKNOWN_ERROR'
  message: string
  timestamp: number
  itemId?: string
  originalError?: Error
}

export function useAudioPlayback() {
  const audioContext = ref<AudioContext | null>(null)
  const gainNode = ref<GainNode | null>(null)
  const currentSource = ref<AudioBufferSourceNode | null>(null)
  
  // Audio queue management
  const audioQueue = ref<AudioQueueItem[]>([])
  const currentPlayingItem = ref<AudioQueueItem | null>(null)
  
  // Playback state
  const state = reactive<PlaybackState>({
    isPlaying: false,
    currentItem: null,
    queueLength: 0,
    playbackPosition: 0,
    volume: 1.0,
    isMuted: false,
    lastError: null,
    errorCount: 0,
    isRecovering: false
  })
  
  // Computed properties
  const hasItemsInQueue = computed(() => audioQueue.value.length > 0)
  const isQueueEmpty = computed(() => audioQueue.value.length === 0)
  const nextItem = computed(() => audioQueue.value[0] || null)
  const hasErrors = computed(() => state.errorCount > 0)
  const isHealthy = computed(() => state.errorCount < 3 && !state.isRecovering)
  
  // Error handling utilities
  const logError = (type: AudioError['type'], message: string, originalError?: Error, itemId?: string): AudioError => {
    const error: AudioError = {
      type,
      message,
      timestamp: Date.now(),
      itemId,
      originalError
    }
    
    state.lastError = error
    state.errorCount++
    
    console.error(`🔊 Audio Error [${type}]:`, message, originalError)
    
    if (itemId) {
      console.error(`📝 Failed item ID: ${itemId}`)
    }
    
    return error
  }
  
  const clearErrors = (): void => {
    state.lastError = null
    state.errorCount = 0
    state.isRecovering = false
    console.log('🔧 Audio errors cleared')
  }
  
  const shouldSkipItem = (error: AudioError): boolean => {
    // Skip items with decode errors - they're likely corrupted
    return error.type === 'DECODE_ERROR'
  }
  
  const shouldRetryItem = (error: AudioError): boolean => {
    // Retry context or playback errors - they might be temporary
    return error.type === 'CONTEXT_ERROR' || error.type === 'PLAYBACK_ERROR'
  }
  
  // Initialize Audio Context and Gain Node
  const initAudioContext = (): AudioContext => {
    try {
      if (!audioContext.value) {
        audioContext.value = new AudioContext()
        
        // Create gain node for volume control
        gainNode.value = audioContext.value.createGain()
        gainNode.value.connect(audioContext.value.destination)
        gainNode.value.gain.value = state.isMuted ? 0 : state.volume
        
        console.log('🎵 Audio context initialized successfully')
      }
      return audioContext.value
    } catch (error) {
      logError('CONTEXT_ERROR', 'Failed to initialize audio context', error as Error)
      throw error
    }
  }
  
  // Audio Context Preparation (to be called after user interaction)
  const prepareAudioContext = async (): Promise<void> => {
    try {
      const context = initAudioContext()
      
      // Resume context if suspended (required by browsers for autoplay policy)
      if (context.state === 'suspended') {
        console.log('🔄 [PREPARE] Resumindo AudioContext suspenso...')
        await context.resume()
        console.log('✅ [PREPARE] AudioContext ativo:', context.state)
      }
      
      console.log('🎵 [PREPARE] AudioContext preparado para reprodução')
    } catch (error) {
      console.error('❌ [PREPARE] Erro ao preparar AudioContext:', error)
      logError('CONTEXT_ERROR', 'Failed to prepare audio context', error as Error)
      throw error
    }
  }

  // Queue Management Methods
  const enqueueAudio = (audioData: ArrayBuffer, metadata?: Record<string, any>): string => {
    try {
      console.log('🔍 [ENQUEUE] Iniciando enfileiramento:', {
        dataSize: audioData?.byteLength || 'null/undefined',
        metadata: metadata,
        queueSizeBefore: audioQueue.value.length,
        isPlaying: state.isPlaying,
        isRecovering: state.isRecovering
      })
      
      // Validate audio data
      if (!audioData || audioData.byteLength === 0) {
        console.error('❌ [ENQUEUE] Dados de áudio inválidos:', { audioData, byteLength: audioData?.byteLength })
        throw new Error('Invalid audio data: empty or null')
      }
      
      const item: AudioQueueItem = {
        id: generateId(),
        audioData: audioData.slice(0), // Create a copy to avoid issues
        timestamp: Date.now(),
        source: metadata?.source || 'websocket',
        metadata: metadata || {}
      }
      
      audioQueue.value.push(item)
      state.queueLength = audioQueue.value.length
      
      console.log(`✅ [ENQUEUE] Áudio enfileirado:`, {
        id: item.id,
        size: item.audioData.byteLength,
        source: item.source,
        queueLength: audioQueue.value.length,
        willStartProcessing: !state.isPlaying && !state.isRecovering
      })
      
      // Try to prepare AudioContext if not already done (fallback)
      if (audioContext.value?.state === 'suspended') {
        console.log('🔄 [ENQUEUE] AudioContext suspenso, tentando preparar...')
        prepareAudioContext().catch(error => {
          console.warn('⚠️ [ENQUEUE] Não foi possível preparar AudioContext automaticamente:', error)
        })
      }
      
      // If nothing is playing, start playing the queue
      if (!state.isPlaying && !state.isRecovering) {
        console.log('▶️ [ENQUEUE] Iniciando processamento da fila...')
        processQueue()
      } else {
        console.log('⏸️ [ENQUEUE] Não iniciando processamento:', {
          isPlaying: state.isPlaying,
          isRecovering: state.isRecovering
        })
      }
      
      return item.id
    } catch (error) {
      console.error('❌ [ENQUEUE] Erro ao enfileirar áudio:', error)
      logError('QUEUE_ERROR', 'Failed to enqueue audio', error as Error)
      throw error
    }
  }
  
  const dequeueAudio = (): AudioQueueItem | null => {
    const item = audioQueue.value.shift() || null
    state.queueLength = audioQueue.value.length
    
    if (item) {
      console.log(`🎵 Audio dequeued: ${item.id}, Remaining: ${audioQueue.value.length}`)
    }
    
    return item
  }
  
  const clearQueue = (): void => {
    console.log(`🗑️ Clearing audio queue: ${audioQueue.value.length} items`)
    audioQueue.value = []
    state.queueLength = 0
    clearErrors() // Clear errors when manually clearing queue
  }
  
  const peekNext = (): AudioQueueItem | null => {
    return audioQueue.value[0] || null
  }
  
  const removeFromQueue = (itemId: string): boolean => {
    const index = audioQueue.value.findIndex(item => item.id === itemId)
    if (index !== -1) {
      audioQueue.value.splice(index, 1)
      state.queueLength = audioQueue.value.length
      console.log(`🗑️ Removed item ${itemId} from queue`)
      return true
    }
    return false
  }
  
  // Audio Playback Methods with Enhanced Error Handling
  const playAudioBuffer = async (audioData: ArrayBuffer, itemId?: string): Promise<void> => {
    try {
      console.log('🎵 [PLAYBACK-START] Iniciando reprodução:', { 
        itemId, 
        dataSize: audioData.byteLength,
        currentlyPlaying: state.isPlaying,
        queueLength: audioQueue.value.length,
        hasCurrentSource: !!currentSource.value
      })
      
      const context = initAudioContext()
      
      // Check if context is ready for playback
      if (context.state === 'suspended') {
        console.error('❌ [PLAYBACK] AudioContext suspenso - deve ser preparado primeiro via interação do usuário')
        throw new Error('AudioContext is suspended - must be prepared first via user interaction')
      }
      
      // Check for overlapping playback and stop if needed
      if (state.isPlaying || currentSource.value) {
        console.warn('⚠️ [PLAYBACK-OVERLAP] Parando reprodução anterior antes de iniciar nova')
        const source = currentSource.value
        if (source) {
          try {
            source.stop()
            source.disconnect()
          } catch (e) {
            console.warn('⚠️ Erro ao parar fonte anterior:', e)
          }
          currentSource.value = null
        }
        state.isPlaying = false
      }
      
      state.isPlaying = true
      
      // Validate audio data before decoding
      if (!audioData || audioData.byteLength === 0) {
        throw new Error('Invalid audio data: empty or null buffer')
      }
      
      console.log(`🎵 Decoding audio data: ${audioData.byteLength} bytes`)
      
      // Decode the audio data with error handling
      let audioBuffer: AudioBuffer
      try {
        audioBuffer = await context.decodeAudioData(audioData.slice(0))
      } catch (decodeError) {
        throw new Error(`Audio decode failed: ${(decodeError as Error).message}`)
      }
      
      // Stop current playback if any
      if (currentSource.value) {
        currentSource.value.stop()
        currentSource.value.disconnect()
      }
      
      // Create buffer source
      const source = context.createBufferSource()
      source.buffer = audioBuffer
      
      // Connect through gain node for volume control
      if (gainNode.value) {
        source.connect(gainNode.value)
      } else {
        source.connect(context.destination)
      }
      
      currentSource.value = source
      
      // Set up completion handler
      source.onended = () => {
        console.log('🎵 Audio playback completed')
        state.isPlaying = false
        state.currentItem = null
        currentSource.value = null
        
        // Process next item in queue
        setTimeout(() => processQueue(), 100) // Small delay to prevent rapid firing
      }
      
      // Start playback
      source.start(0)
      
      console.log(`🎵 Playing audio buffer: ${audioBuffer.duration.toFixed(2)}s, ${audioBuffer.numberOfChannels} channel(s), ${audioBuffer.sampleRate}Hz`)
      
    } catch (error) {
      const errorMsg = (error as Error).message
      
      // Categorize the error
      let errorType: AudioError['type'] = 'UNKNOWN_ERROR'
      if (errorMsg.includes('decode') || errorMsg.includes('Encoding')) {
        errorType = 'DECODE_ERROR'
      } else if (errorMsg.includes('context') || errorMsg.includes('suspended')) {
        errorType = 'CONTEXT_ERROR'
      } else {
        errorType = 'PLAYBACK_ERROR'
      }
      
      logError(errorType, `Playback failed: ${errorMsg}`, error as Error, itemId)
      
      state.isPlaying = false
      state.currentItem = null
      currentSource.value = null
      
      throw error
    }
  }
  
  // Queue Processing with Recovery Logic
  const processQueue = async (): Promise<void> => {
    console.log('🔍 [PROCESS-QUEUE] Verificando condições:', {
      isPlaying: state.isPlaying,
      queueEmpty: isQueueEmpty.value,
      queueLength: audioQueue.value.length,
      errorCount: state.errorCount,
      isRecovering: state.isRecovering
    })
    
    if (state.isPlaying || isQueueEmpty.value) {
      console.log('⏸️ [PROCESS-QUEUE] Interrompendo processamento:', {
        reason: state.isPlaying ? 'already playing' : 'queue empty'
      })
      return
    }
    
    // Check if we need to recover from errors
    if (state.errorCount >= 5) {
      console.warn('⚠️ [PROCESS-QUEUE] Muitos erros, pausando processamento')
      state.isRecovering = true
      return
    }
    
    const nextItem = dequeueAudio()
    if (!nextItem) {
      console.log('⚠️ [PROCESS-QUEUE] Nenhum item retornado pela dequeue')
      return
    }
    
    console.log('🎵 [PROCESS-QUEUE] Processando item:', {
      id: nextItem.id,
      source: nextItem.source,
      dataSize: nextItem.audioData.byteLength,
      retryCount: nextItem.metadata?.retryCount || 0,
      isStreaming: nextItem.source === 'websocket-streaming' || nextItem.metadata?.streaming === true
    })
    
    try {
      state.currentItem = nextItem
      currentPlayingItem.value = nextItem
      
      console.log(`🎵 Processing queue item: ${nextItem.id}`)
      await playAudioBuffer(nextItem.audioData, nextItem.id)
      
      // Reset error count on successful playback
      if (state.errorCount > 0) {
        console.log('✅ Successful playback, reducing error count')
        state.errorCount = Math.max(0, state.errorCount - 1)
      }
      
    } catch (error) {
      const audioError = state.lastError!
      
      console.error(`❌ Error processing queue item ${nextItem.id}:`, error)
      
      // Decide recovery strategy based on error type
      if (shouldSkipItem(audioError)) {
        console.log(`⏭️ Skipping corrupted item ${nextItem.id}`)
        // Continue with next item immediately
        state.isPlaying = false
        state.currentItem = null
        setTimeout(() => processQueue(), 100)
        
      } else if (shouldRetryItem(audioError) && (nextItem.metadata?.retryCount || 0) < 2) {
        // Check if this is a streaming chunk - don't retry streaming chunks to avoid repetition
        const isStreamingChunk = nextItem.source === 'websocket-streaming' || nextItem.metadata?.streaming === true
        
        if (isStreamingChunk) {
          console.log(`⏭️ Skipping streaming chunk ${nextItem.id} (no retry for streaming)`)
          // Continue with next item immediately for streaming chunks
          state.isPlaying = false
          state.currentItem = null
          setTimeout(() => processQueue(), 100)
        } else {
          console.log(`🔄 Retrying item ${nextItem.id}`)
          // Retry the same item with increased retry count
          nextItem.metadata = nextItem.metadata || {}
          nextItem.metadata.retryCount = (nextItem.metadata.retryCount || 0) + 1
          
          // Re-queue the item at the front
          audioQueue.value.unshift(nextItem)
          state.queueLength = audioQueue.value.length
          
          state.isPlaying = false
          state.currentItem = null
          
          // Wait longer before retry
          setTimeout(() => processQueue(), 1000)
        }
        
      } else {
        console.log(`❌ Giving up on item ${nextItem.id} after retries`)
        // Continue with next item even if current one failed
        state.isPlaying = false
        state.currentItem = null
        setTimeout(() => processQueue(), 500)
      }
    }
  }
  
  // Recovery methods
  const recoverFromErrors = async (): Promise<void> => {
    console.log('🔧 Starting error recovery process...')
    
    state.isRecovering = true
    
    try {
      // Stop current playback
      stopPlayback()
      
      // Reset audio context
      if (audioContext.value) {
        await audioContext.value.close()
        audioContext.value = null
        gainNode.value = null
      }
      
      // Clear errors
      clearErrors()
      
      // Reinitialize
      initAudioContext()
      
      console.log('✅ Error recovery completed')
      
      // Resume queue processing if items are available
      if (hasItemsInQueue.value) {
        setTimeout(() => processQueue(), 500)
      }
      
    } catch (error) {
      console.error('❌ Error recovery failed:', error)
      logError('CONTEXT_ERROR', 'Recovery failed', error as Error)
    } finally {
      state.isRecovering = false
    }
  }
  
  // Volume and Mute Controls
  const setVolume = (volume: number): void => {
    const clampedVolume = Math.max(0, Math.min(1, volume))
    state.volume = clampedVolume
    
    if (gainNode.value && !state.isMuted) {
      gainNode.value.gain.value = clampedVolume
    }
    
    console.log(`🔊 Volume set to: ${(clampedVolume * 100).toFixed(0)}%`)
  }
  
  const toggleMute = (): void => {
    state.isMuted = !state.isMuted
    
    if (gainNode.value) {
      gainNode.value.gain.value = state.isMuted ? 0 : state.volume
    }
    
    console.log(`🔊 Audio ${state.isMuted ? 'muted' : 'unmuted'}`)
  }
  
  // Playback Control
  const stopPlayback = (): void => {
    if (currentSource.value) {
      try {
        currentSource.value.stop()
        currentSource.value.disconnect()
      } catch (error) {
        console.warn('⚠️ Error stopping audio source:', error)
      }
      currentSource.value = null
    }
    
    state.isPlaying = false
    state.currentItem = null
    currentPlayingItem.value = null
    
    console.log('⏹️ Playback stopped')
  }
  
  const pauseQueue = (): void => {
    stopPlayback()
    console.log('⏸️ Queue paused')
  }
  
  const resumeQueue = (): void => {
    if (!state.isPlaying && hasItemsInQueue.value && !state.isRecovering) {
      processQueue()
      console.log('▶️ Queue resumed')
    }
  }
  
  // Cleanup
  const cleanup = (): void => {
    stopPlayback()
    clearQueue()
    
    if (audioContext.value) {
      audioContext.value.close()
      audioContext.value = null
    }
    
    gainNode.value = null
    clearErrors()
    console.log('🧹 Audio playback cleanup completed')
  }
  
  // Utility Functions
  const generateId = (): string => {
    return `audio_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
  }
  
  const getQueueInfo = () => {
    return {
      total: audioQueue.value.length,
      items: audioQueue.value.map(item => ({
        id: item.id,
        timestamp: item.timestamp,
        source: item.source,
        metadata: item.metadata
      })),
      currentItem: currentPlayingItem.value ? {
        id: currentPlayingItem.value.id,
        timestamp: currentPlayingItem.value.timestamp,
        source: currentPlayingItem.value.source
      } : null,
      errors: {
        hasErrors: hasErrors.value,
        errorCount: state.errorCount,
        lastError: state.lastError,
        isHealthy: isHealthy.value,
        isRecovering: state.isRecovering
      }
    }
  }
  
  const getErrorReport = () => {
    return {
      errorCount: state.errorCount,
      lastError: state.lastError,
      isRecovering: state.isRecovering,
      isHealthy: isHealthy.value,
      recommendations: getRecommendations()
    }
  }
  
  const getRecommendations = (): string[] => {
    const recommendations: string[] = []
    
    if (state.errorCount > 3) {
      recommendations.push('Consider clearing the queue and restarting')
    }
    
    if (state.lastError?.type === 'DECODE_ERROR') {
      recommendations.push('Check audio format compatibility')
    }
    
    if (state.lastError?.type === 'CONTEXT_ERROR') {
      recommendations.push('Try refreshing the page to reset audio context')
    }
    
    if (!isHealthy.value) {
      recommendations.push('Use the recovery function to reset the audio system')
    }
    
    return recommendations
  }
  
  return {
    // State
    state: readonly(state),
    
    // Audio context preparation
    prepareAudioContext,
    
    // Queue management
    enqueueAudio,
    dequeueAudio,
    clearQueue,
    peekNext,
    removeFromQueue,
    
    // Playback control
    playAudioBuffer,
    stopPlayback,
    pauseQueue,
    resumeQueue,
    
    // Volume control
    setVolume,
    toggleMute,
    
    // Error handling
    clearErrors,
    recoverFromErrors,
    getErrorReport,
    
    // Computed properties
    hasItemsInQueue,
    isQueueEmpty,
    nextItem,
    hasErrors,
    isHealthy,
    
    // Utility
    getQueueInfo,
    cleanup
  }
} 