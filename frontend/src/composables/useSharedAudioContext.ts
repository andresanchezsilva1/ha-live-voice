/**
 * Shared Audio Context composable
 * Gerencia um único AudioContext para toda a aplicação
 * Evita conflitos entre VAD, AudioStreamer e outros componentes de áudio
 */

import { ref, watch } from 'vue'

// AudioContext compartilhado global
let sharedAudioContext: AudioContext | null = null
const isReady = ref(false)
const isResuming = ref(false)

export function useSharedAudioContext() {
  
  /**
   * Inicializar o AudioContext compartilhado
   */
  const initializeAudioContext = async (): Promise<AudioContext> => {
    try {
      if (!sharedAudioContext) {
        console.log('🎵 [SHARED-AUDIO] Criando AudioContext compartilhado...')
        sharedAudioContext = new (window.AudioContext || (window as any).webkitAudioContext)()
        
        // Listen for state changes
        const handleStateChange = () => {
          console.log('🎵 [SHARED-AUDIO] AudioContext state:', sharedAudioContext?.state)
          isReady.value = sharedAudioContext?.state === 'running'
        }
        
        // Monitor state changes
        sharedAudioContext.addEventListener('statechange', handleStateChange)
        
        console.log('✅ [SHARED-AUDIO] AudioContext criado:', {
          state: sharedAudioContext.state,
          sampleRate: sharedAudioContext.sampleRate,
          baseLatency: sharedAudioContext.baseLatency,
          outputLatency: sharedAudioContext.outputLatency
        })
      }
      
      // Ensure AudioContext is running
      if (sharedAudioContext.state === 'suspended') {
        console.log('🎵 [SHARED-AUDIO] AudioContext suspenso, resumindo...')
        isResuming.value = true
        await sharedAudioContext.resume()
        isResuming.value = false
        console.log('✅ [SHARED-AUDIO] AudioContext resumido')
      }
      
      isReady.value = sharedAudioContext.state === 'running'
      return sharedAudioContext
      
    } catch (error) {
      console.error('❌ [SHARED-AUDIO] Erro ao inicializar AudioContext:', error)
      isReady.value = false
      throw error
    }
  }

  /**
   * Obter o AudioContext compartilhado (cria se necessário)
   */
  const getAudioContext = async (): Promise<AudioContext> => {
    if (!sharedAudioContext || sharedAudioContext.state === 'closed') {
      return await initializeAudioContext()
    }
    
    if (sharedAudioContext.state === 'suspended') {
      isResuming.value = true
      await sharedAudioContext.resume()
      isResuming.value = false
    }
    
    isReady.value = sharedAudioContext.state === 'running'
    return sharedAudioContext
  }

  /**
   * Forçar retomada do AudioContext (útil para interação do usuário)
   */
  const resumeAudioContext = async (): Promise<void> => {
    try {
      const context = await getAudioContext()
      if (context.state === 'suspended') {
        console.log('🎵 [SHARED-AUDIO] Forçando retomada do AudioContext...')
        isResuming.value = true
        await context.resume()
        isResuming.value = false
        console.log('✅ [SHARED-AUDIO] AudioContext retomado com sucesso')
      }
      isReady.value = context.state === 'running'
    } catch (error) {
      console.error('❌ [SHARED-AUDIO] Erro ao retomar AudioContext:', error)
      isReady.value = false
      throw error
    }
  }

  /**
   * Verificar se o AudioContext está pronto
   */
  const ensureAudioContextReady = async (): Promise<boolean> => {
    try {
      const context = await getAudioContext()
      const ready = context.state === 'running'
      isReady.value = ready
      
      if (!ready) {
        console.warn('⚠️ [SHARED-AUDIO] AudioContext não está pronto:', context.state)
      }
      
      return ready
    } catch (error) {
      console.error('❌ [SHARED-AUDIO] Erro ao verificar AudioContext:', error)
      isReady.value = false
      return false
    }
  }

  /**
   * Destruir o AudioContext compartilhado (cleanup)
   */
  const destroyAudioContext = async (): Promise<void> => {
    if (sharedAudioContext && sharedAudioContext.state !== 'closed') {
      console.log('🎵 [SHARED-AUDIO] Fechando AudioContext compartilhado...')
      await sharedAudioContext.close()
      sharedAudioContext = null
      isReady.value = false
      console.log('✅ [SHARED-AUDIO] AudioContext fechado')
    }
  }

  /**
   * Obter informações do AudioContext atual
   */
  const getContextInfo = () => {
    if (!sharedAudioContext) {
      return null
    }
    
    return {
      state: sharedAudioContext.state,
      sampleRate: sharedAudioContext.sampleRate,
      currentTime: sharedAudioContext.currentTime,
      baseLatency: sharedAudioContext.baseLatency,
      outputLatency: sharedAudioContext.outputLatency
    }
  }

  return {
    // Estado
    isReady,
    isResuming,
    
    // Métodos principais
    getAudioContext,
    initializeAudioContext,
    resumeAudioContext,
    ensureAudioContextReady,
    destroyAudioContext,
    
    // Utilitários
    getContextInfo
  }
} 