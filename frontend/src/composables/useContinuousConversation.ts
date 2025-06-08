/**
 * Continuous Conversation composable
 * Integra VAD com WebSocket para conversa natural e contínua
 */

import { ref, computed, watch } from 'vue'
import { useAudioWorklet } from './useAudioWorklet'
import { useWebSocketAudio } from './useWebSocketAudio'
import { useAppStore } from '../store/appStore'
import { useSharedAudioContext } from './useSharedAudioContext'

export type ConversationState = 'idle' | 'listening' | 'speaking' | 'processing' | 'assistant_speaking' | 'muted'

export interface ConversationConfig {
  // VAD configuration
  vadConfig?: {
    volumeThreshold?: number
    silenceTimeout?: number
    voiceTimeout?: number
  }
  // Auto-connect on start
  autoConnect?: boolean
  // WebSocket URL
  wsUrl: string
}

export function useContinuousConversation(config: ConversationConfig) {
  const store = useAppStore()
  const { resumeAudioContext, ensureAudioContextReady } = useSharedAudioContext()
  
  // Estado da conversa
  const conversationState = ref<ConversationState>('idle')
  const isMuted = ref(false)
  const isConnected = ref(false)
  const assistantVolume = ref(0.8)

  // Integração com AudioWorklet VAD
  const audioWorklet = useAudioWorklet({
    volumeThreshold: config.vadConfig?.volumeThreshold || 0.008,
    silenceTimeout: config.vadConfig?.silenceTimeout || 2500,
    voiceTimeout: config.vadConfig?.voiceTimeout || 300,
    sampleRate: 16000
  })
  
  // Integração com WebSocket
  const websocket = useWebSocketAudio(config.wsUrl)

  // Estado computado
  const canSpeak = computed(() => 
    isConnected.value && 
    !isMuted.value && 
    conversationState.value !== 'assistant_speaking' &&
    conversationState.value !== 'processing'
  )

  const statusText = computed(() => {
    switch (conversationState.value) {
      case 'idle':
        return isMuted.value ? 'Microfone mutado' : 'Aguardando...'
      case 'listening':
        return 'Ouvindo...'
      case 'speaking':
        return 'Falando...'
      case 'processing':
        return 'Processando...'
      case 'assistant_speaking':
        return 'Assistente falando...'
      case 'muted':
        return 'Microfone mutado'
      default:
        return 'Desconectado'
    }
  })

  const statusColor = computed(() => {
    switch (conversationState.value) {
      case 'listening':
        return 'blue'
      case 'speaking':
        return 'green'
      case 'processing':
        return 'yellow'
      case 'assistant_speaking':
        return 'purple'
      case 'muted':
        return 'gray'
      default:
        return 'gray'
    }
  })

  /**
   * Iniciar conversa contínua
   */
  const startConversation = async (): Promise<void> => {
    try {
      console.log('🎯 [CONVERSATION] Iniciando conversa contínua...')
      
      // Garantir que o AudioContext está pronto antes de tudo
      await resumeAudioContext()
      await ensureAudioContextReady()
      
      // Conectar WebSocket primeiro
      await websocket.connect()
      isConnected.value = true
      
      // Configurar callbacks do AudioWorklet
      audioWorklet.setCallbacks({
        onVoiceStart: handleVoiceStart,
        onVoiceEnd: handleVoiceEnd,
        onVolumeChange: handleVolumeChange
      })
      
      // Iniciar AudioWorklet
      await audioWorklet.startWorklet()
      
      // Configurar estado inicial
      updateConversationState()
      
      // Auto-conectar se configurado
      if (config.autoConnect) {
        console.log('🔗 [CONVERSATION] Auto-conectando...')
      }
      
      console.log('✅ [CONVERSATION] Conversa contínua iniciada')
      store.addNotification('status', 'Conversa contínua ativada')
      
    } catch (error) {
      console.error('❌ [CONVERSATION] Erro ao iniciar conversa:', error)
      store.setError('CONVERSATION_ERROR', 'Erro ao iniciar conversa', (error as Error).message)
      throw error
    }
  }

  /**
   * Parar conversa contínua
   */
  const stopConversation = (): void => {
    try {
      console.log('🛑 [CONVERSATION] Parando conversa contínua...')
      
      // Parar gravação se ativa
      if (websocket.isRecording.value) {
        websocket.stopAudioRecording()
      }
      
      // Parar AudioWorklet
      audioWorklet.stopWorklet()
      
      // Desconectar WebSocket
      websocket.disconnect()
      isConnected.value = false
      
      // Resetar estado
      conversationState.value = 'idle'
      
      console.log('✅ [CONVERSATION] Conversa contínua parada')
      store.addNotification('status', 'Conversa contínua desativada')
      
    } catch (error) {
      console.error('❌ [CONVERSATION] Erro ao parar conversa:', error)
    }
  }

  /**
   * Toggle mute/unmute
   */
  const toggleMute = (): void => {
    isMuted.value = !isMuted.value
    
    if (isMuted.value) {
      console.log('🔇 [CONVERSATION] Microfone mutado')
      // Parar gravação se ativa
      if (websocket.isRecording.value) {
        websocket.stopAudioRecording()
      }
      store.addNotification('status', 'Microfone mutado')
    } else {
      console.log('🎤 [CONVERSATION] Microfone ativado')
      store.addNotification('status', 'Microfone ativado')
    }
    
    updateConversationState()
  }

  /**
   * Callback: Voz detectada
   */
  const handleVoiceStart = async (): Promise<void> => {
    console.log('🎤 [CONVERSATION] VAD detectou início de voz')
    
    if (!canSpeak.value) {
      console.log('⚠️ [CONVERSATION] Voz detectada mas não pode falar:', {
        isConnected: isConnected.value,
        isMuted: isMuted.value,
        state: conversationState.value,
        canSpeak: canSpeak.value
      })
      return
    }

    try {
      console.log('🎤 [CONVERSATION] Iniciando gravação por voz detectada')
      console.log('🔍 [CONVERSATION] Estado antes da gravação:', {
        websocketState: websocket.websocket.value?.readyState,
        isRecording: websocket.isRecording.value,
        isConnected: isConnected.value
      })
      
      conversationState.value = 'speaking'
      await websocket.startAudioRecording()
      
      console.log('✅ [CONVERSATION] Gravação iniciada com sucesso')
    } catch (error) {
      console.error('❌ [CONVERSATION] Erro ao iniciar gravação:', error)
      conversationState.value = 'listening'
    }
  }

  /**
   * Callback: Fim da voz detectada
   */
  const handleVoiceEnd = (): void => {
    console.log('🔇 [CONVERSATION] VAD detectou fim de voz')
    
    if (websocket.isRecording.value) {
      console.log('🔇 [CONVERSATION] Parando gravação por fim da voz')
      conversationState.value = 'processing'
      websocket.stopAudioRecording()
      
      // Depois de um tempo, voltar para listening se não houver resposta
      setTimeout(() => {
        if (conversationState.value === 'processing') {
          console.log('⏰ [CONVERSATION] Timeout de processamento, voltando para listening')
          updateConversationState()
        }
      }, 5000) // 5s timeout
    } else {
      console.log('⚠️ [CONVERSATION] Fim de voz detectado mas não estava gravando')
    }
  }

  /**
   * Callback: Mudança de volume
   */
  const handleVolumeChange = (volume: number): void => {
    // Pode ser usado para feedback visual (VU meter)
    // console.log('📊 [CONVERSATION] Volume:', volume)
  }

  /**
   * Atualizar estado da conversa baseado nas condições atuais
   */
  const updateConversationState = (): void => {
    if (!isConnected.value) {
      conversationState.value = 'idle'
    } else if (isMuted.value) {
      conversationState.value = 'muted'
    } else if (websocket.isRecording.value) {
      conversationState.value = 'speaking'
    } else if (websocket.playbackState.isPlaying) {
      conversationState.value = 'assistant_speaking'
    } else if (audioWorklet.isListening.value) {
      conversationState.value = 'listening'
    } else {
      conversationState.value = 'idle'
    }
  }

  /**
   * Configurar volume do assistente
   */
  const setAssistantVolume = (volume: number): void => {
    assistantVolume.value = Math.max(0, Math.min(1, volume))
    websocket.setVolume(assistantVolume.value)
  }

  /**
   * Toggle mute do assistente
   */
  const toggleAssistantMute = (): void => {
    websocket.toggleMute()
  }

  // Watchers para sincronizar estados
  watch(() => websocket.isRecording.value, () => {
    updateConversationState()
  })

  watch(() => websocket.playbackState.isPlaying, async (isPlaying, wasPlaying) => {
    updateConversationState()
    
    // Quando o assistente termina de falar, garantir que o VAD está funcionando
    if (wasPlaying && !isPlaying && isConnected.value) {
      console.log('🎤 [CONVERSATION] Assistente terminou de falar, reativando VAD...')
      try {
        // Pequeno delay para garantir que o áudio finalizou completamente
        await new Promise(resolve => setTimeout(resolve, 500))
        
        // Garantir que o AudioContext está ativo
        await resumeAudioContext()
        await ensureAudioContextReady()
        
        // Se o AudioWorklet não está funcionando, reiniciar
        if (!audioWorklet.isListening.value && !isMuted.value) {
          console.log('🔄 [CONVERSATION] Reiniciando AudioWorklet após reprodução do assistente')
          audioWorklet.stopWorklet()
          await audioWorklet.startWorklet()
        }
        
        console.log('✅ [CONVERSATION] AudioWorklet reativado com sucesso')
      } catch (error) {
        console.error('❌ [CONVERSATION] Erro ao reativar AudioWorklet:', error)
      }
    }
  })

  watch(() => audioWorklet.isListening.value, () => {
    updateConversationState()
  })

  watch(() => websocket.websocket.value?.readyState, (newState) => {
    isConnected.value = newState === WebSocket.OPEN
    updateConversationState()
  })

  // Cleanup ao desmontar
  const cleanup = (): void => {
    stopConversation()
    websocket.cleanup()
  }

  return {
    // Estado
    conversationState,
    isMuted,
    isConnected,
    assistantVolume,
    
    // Estado computado
    canSpeak,
    statusText,
    statusColor,
    
    // Estados dos composables
    vadState: audioWorklet.workletState,
    playbackState: websocket.playbackState,
    
    // Métodos principais
    startConversation,
    stopConversation,
    toggleMute,
    
    // Controles do assistente
    setAssistantVolume,
    toggleAssistantMute,
    
    // Configuração
    updateVadConfig: audioWorklet.updateConfig,
    
    // Debug/manual
    forceSpeaking: audioWorklet.forceSpeaking,
    
    // Cleanup
    cleanup
  }
} 