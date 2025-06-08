import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface AudioStatus {
  isRecording: boolean
  isPlaying: boolean
  isConnected: boolean
  volume: number
  isMuted: boolean
}

export interface SystemMessage {
  type: 'transcription' | 'response' | 'error' | 'status'
  content: string
  timestamp: number
}

export interface AppError {
  code: string
  message: string
  details?: string
  timestamp: number
}

export const useAppStore = defineStore('app', () => {
  // Estados reativos
  const isConnected = ref(false)
  const isRecording = ref(false)
  const isPlaying = ref(false)
  const volume = ref(1.0)
  const isMuted = ref(false)
  
  // Mensagens e conteúdo
  const transcription = ref('')
  const systemResponse = ref('')
  const messages = ref<SystemMessage[]>([])
  
  // Estados de interface
  const isConnecting = ref(false)
  const isInitializing = ref(false)
  const currentView = ref('home')
  
  // Erros e notificações
  const error = ref<AppError | null>(null)
  const errorHistory = ref<AppError[]>([])
  const notifications = ref<SystemMessage[]>([])

  // Computed properties
  const audioStatus = computed<AudioStatus>(() => ({
    isRecording: isRecording.value,
    isPlaying: isPlaying.value,
    isConnected: isConnected.value,
    volume: volume.value,
    isMuted: isMuted.value
  }))

  const hasError = computed(() => error.value !== null)
  const hasMessages = computed(() => messages.value.length > 0)
  const hasNotifications = computed(() => notifications.value.length > 0)
  const canRecord = computed(() => isConnected.value && !isRecording.value)
  const canConnect = computed(() => !isConnected.value && !isConnecting.value)

  const latestMessage = computed(() => {
    return messages.value.length > 0 ? messages.value[messages.value.length - 1] : null
  })

  // Actions para gerenciar estado de conexão
  const setConnectionStatus = (status: boolean) => {
    isConnected.value = status
    if (status) {
      isConnecting.value = false
      clearError()
    }
  }

  const setConnectingStatus = (status: boolean) => {
    isConnecting.value = status
    if (status) {
      clearError()
    }
  }

  // Actions para gerenciar estado de áudio
  const setRecordingStatus = (status: boolean) => {
    isRecording.value = status
  }

  const setPlayingStatus = (status: boolean) => {
    isPlaying.value = status
  }

  const setVolume = (newVolume: number) => {
    volume.value = Math.max(0, Math.min(1, newVolume))
    if (newVolume > 0) {
      isMuted.value = false
    }
  }

  const toggleMute = () => {
    isMuted.value = !isMuted.value
  }

  // Actions para gerenciar conteúdo
  const updateTranscription = (text: string) => {
    transcription.value = text
    addMessage('transcription', text)
  }

  const updateSystemResponse = (text: string | any) => {
    // Garantir que seja sempre uma string
    let responseText = text
    if (typeof text !== 'string') {
      if (text instanceof Blob) {
        responseText = '[Dados de áudio recebidos]'
      } else {
        responseText = String(text)
      }
    }
    
    systemResponse.value = responseText
    addMessage('response', responseText)
  }

  const appendTranscription = (text: string) => {
    transcription.value += text
  }

  const clearTranscription = () => {
    transcription.value = ''
  }

  const clearSystemResponse = () => {
    systemResponse.value = ''
  }

  // Actions para gerenciar mensagens
  const addMessage = (type: SystemMessage['type'], content: string) => {
    const message: SystemMessage = {
      type,
      content,
      timestamp: Date.now()
    }
    messages.value.push(message)
    
    // Manter apenas as últimas 100 mensagens
    if (messages.value.length > 100) {
      messages.value = messages.value.slice(-100)
    }
  }

  const clearMessages = () => {
    messages.value = []
  }

  // Actions para gerenciar erros
  const setError = (code: string, message: string, details?: string) => {
    const newError: AppError = {
      code,
      message,
      details,
      timestamp: Date.now()
    }
    
    error.value = newError
    errorHistory.value.push(newError)
    
    // Manter apenas os últimos 20 erros no histórico
    if (errorHistory.value.length > 20) {
      errorHistory.value = errorHistory.value.slice(-20)
    }
    
    // Adicionar erro como notificação
    addNotification('error', `${code}: ${message}`)
  }

  const clearError = () => {
    error.value = null
  }

  // Actions para gerenciar notificações
  const addNotification = (type: SystemMessage['type'], content: string) => {
    const notification: SystemMessage = {
      type,
      content,
      timestamp: Date.now()
    }
    notifications.value.push(notification)
    
    // Auto-remover notificações após 5 segundos
    setTimeout(() => {
      removeNotification(notification.timestamp)
    }, 5000)
  }

  const removeNotification = (timestamp: number) => {
    const index = notifications.value.findIndex(n => n.timestamp === timestamp)
    if (index !== -1) {
      notifications.value.splice(index, 1)
    }
  }

  const clearNotifications = () => {
    notifications.value = []
  }

  // Actions para gerenciar estado da interface
  const setInitializingStatus = (status: boolean) => {
    isInitializing.value = status
  }

  const setCurrentView = (view: string) => {
    currentView.value = view
  }

  // Action para reset completo do estado
  const resetState = () => {
    isConnected.value = false
    isRecording.value = false
    isPlaying.value = false
    isConnecting.value = false
    isInitializing.value = false
    volume.value = 1.0
    isMuted.value = false
    
    transcription.value = ''
    systemResponse.value = ''
    messages.value = []
    
    error.value = null
    notifications.value = []
    currentView.value = 'home'
  }

  // Action para reset apenas do áudio
  const resetAudioState = () => {
    isRecording.value = false
    isPlaying.value = false
    transcription.value = ''
    systemResponse.value = ''
  }

  return {
    // Estados
    isConnected,
    isRecording,
    isPlaying,
    volume,
    isMuted,
    transcription,
    systemResponse,
    messages,
    isConnecting,
    isInitializing,
    currentView,
    error,
    errorHistory,
    notifications,

    // Computed
    audioStatus,
    hasError,
    hasMessages,
    hasNotifications,
    canRecord,
    canConnect,
    latestMessage,

    // Actions
    setConnectionStatus,
    setConnectingStatus,
    setRecordingStatus,
    setPlayingStatus,
    setVolume,
    toggleMute,
    updateTranscription,
    updateSystemResponse,
    appendTranscription,
    clearTranscription,
    clearSystemResponse,
    addMessage,
    clearMessages,
    setError,
    clearError,
    addNotification,
    removeNotification,
    clearNotifications,
    setInitializingStatus,
    setCurrentView,
    resetState,
    resetAudioState
  }
}) 