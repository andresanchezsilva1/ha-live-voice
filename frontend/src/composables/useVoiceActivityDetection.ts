/**
 * Voice Activity Detection (VAD) composable
 * Detecta quando o usuário está falando para iniciar/parar gravação automaticamente
 */

import { ref, computed } from 'vue'
import { useSharedAudioContext } from './useSharedAudioContext'

export interface VADConfig {
  // Limiar de volume para detectar voz (0-1)
  volumeThreshold: number
  // Tempo mínimo de silêncio para parar gravação (ms)
  silenceTimeout: number
  // Tempo mínimo de fala para confirmar que é voz (ms)
  voiceTimeout: number
  // Intervalo de análise de áudio (ms)
  analysisInterval: number
}

export interface VADState {
  isListening: boolean
  isSpeaking: boolean
  volume: number
  lastVoiceActivity: number
}

export function useVoiceActivityDetection(config: Partial<VADConfig> = {}) {
  // Configuração padrão
  const vadConfig: VADConfig = {
    volumeThreshold: 0.01, // 1% de volume mínimo
    silenceTimeout: 1500,  // 1.5s de silêncio para parar
    voiceTimeout: 200,     // 200ms de voz para confirmar
    analysisInterval: 100, // Análise a cada 100ms
    ...config
  }

  // Estado do VAD
  const isListening = ref(false)
  const isSpeaking = ref(false)
  const currentVolume = ref(0)
  const lastVoiceActivity = ref(0)

  // Usar AudioContext compartilhado
  const { getAudioContext, ensureAudioContextReady } = useSharedAudioContext()

  // Recursos Web Audio
  let audioContext: AudioContext | null = null
  let analyser: AnalyserNode | null = null
  let microphone: MediaStreamAudioSourceNode | null = null
  let dataArray: Uint8Array | null = null
  let stream: MediaStream | null = null
  
  // Timers
  let analysisTimer: number | null = null
  let silenceTimer: number | null = null
  let voiceTimer: number | null = null

  // Estado computado
  const vadState = computed<VADState>(() => ({
    isListening: isListening.value,
    isSpeaking: isSpeaking.value,
    volume: currentVolume.value,
    lastVoiceActivity: lastVoiceActivity.value
  }))

  // Callbacks
  let onVoiceStart: (() => void) | null = null
  let onVoiceEnd: (() => void) | null = null
  let onVolumeChange: ((volume: number) => void) | null = null

  /**
   * Inicializar VAD
   */
  const startVAD = async (): Promise<void> => {
    try {
      console.log('🎤 [VAD] Iniciando Voice Activity Detection...')
      
      // Usar AudioContext compartilhado
      audioContext = await getAudioContext()
      await ensureAudioContextReady()
      
      // Solicitar acesso ao microfone
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          sampleRate: 16000
        }
      })

      // Configurar analisador
      analyser = audioContext.createAnalyser()
      microphone = audioContext.createMediaStreamSource(stream)

      // Configurar analisador
      analyser.fftSize = 256
      analyser.smoothingTimeConstant = 0.8
      const bufferLength = analyser.frequencyBinCount
      dataArray = new Uint8Array(bufferLength)

      // Conectar microfone ao analisador
      microphone.connect(analyser)
      
      isListening.value = true
      startAnalysis()
      
      console.log('✅ [VAD] Voice Activity Detection iniciado com AudioContext compartilhado')
    } catch (error) {
      console.error('❌ [VAD] Erro ao iniciar VAD:', error)
      throw error
    }
  }

  /**
   * Parar VAD
   */
  const stopVAD = (): void => {
    try {
      console.log('🛑 [VAD] Parando Voice Activity Detection...')
      
      // Parar análise
      if (analysisTimer) {
        clearInterval(analysisTimer)
        analysisTimer = null
      }
      
      // Limpar timers
      clearTimers()
      
      // Fechar recursos de áudio
      if (microphone) {
        microphone.disconnect()
        microphone = null
      }
      
      // Não fechar o AudioContext compartilhado, apenas desconectar nossos nós
      if (audioContext) {
        audioContext = null
      }
      
      if (stream) {
        stream.getTracks().forEach(track => track.stop())
        stream = null
      }
      
      // Resetar estado
      isListening.value = false
      isSpeaking.value = false
      currentVolume.value = 0
      analyser = null
      dataArray = null
      
      console.log('✅ [VAD] Voice Activity Detection parado')
    } catch (error) {
      console.error('❌ [VAD] Erro ao parar VAD:', error)
    }
  }

  /**
   * Iniciar análise contínua de volume
   */
  const startAnalysis = (): void => {
    if (!analyser || !dataArray) return

    analysisTimer = setInterval(() => {
      analyzeVolume()
    }, vadConfig.analysisInterval)
  }

  /**
   * Analisar volume do microfone
   */
  const analyzeVolume = (): void => {
    if (!analyser || !dataArray || !audioContext) return
    
    // Verificar se o AudioContext foi suspenso e tentar reativar
    if (audioContext.state === 'suspended') {
      console.warn('⚠️ [VAD] AudioContext suspenso, tentando reativar...')
      audioContext.resume().then(() => {
        console.log('✅ [VAD] AudioContext reativado')
      }).catch(error => {
        console.error('❌ [VAD] Erro ao reativar AudioContext:', error)
      })
      return
    }

    // Obter dados de frequência
    analyser.getByteFrequencyData(dataArray)
    
    // Calcular volume médio
    let sum = 0
    for (let i = 0; i < dataArray.length; i++) {
      sum += dataArray[i]
    }
    const averageVolume = sum / dataArray.length / 255 // Normalizar 0-1
    
    currentVolume.value = averageVolume
    
    // Log periódico para debug (a cada ~3 segundos, mais frequente para debug)
    if (Math.random() < 0.03) { // ~3% de chance = ~1 log a cada 3s
      console.log(`🔊 [VAD] Volume atual: ${(averageVolume * 100).toFixed(1)}% | Limiar: ${(vadConfig.volumeThreshold * 100).toFixed(1)}% | Falando: ${isSpeaking.value} | Ouvindo: ${isListening.value} | AudioContext: ${audioContext?.state}`)
    }
    
    // Callback de volume
    if (onVolumeChange) {
      onVolumeChange(averageVolume)
    }

    // Detectar atividade de voz
    if (averageVolume > vadConfig.volumeThreshold) {
      handleVoiceActivity()
    } else {
      handleSilence()
    }
  }

  /**
   * Lidar com atividade de voz detectada
   */
  const handleVoiceActivity = (): void => {
    lastVoiceActivity.value = Date.now()

    // Limpar timer de silêncio
    if (silenceTimer) {
      clearTimeout(silenceTimer)
      silenceTimer = null
    }

    // Se não está falando ainda, iniciar timer para confirmar voz
    if (!isSpeaking.value && !voiceTimer) {
      console.log(`🎤 [VAD] Volume acima do limiar detectado (${(currentVolume.value * 100).toFixed(1)}%) - aguardando confirmação...`)
      voiceTimer = setTimeout(() => {
        if (!isSpeaking.value) {
          console.log('🎤 [VAD] Voz confirmada - iniciando gravação')
          isSpeaking.value = true
          if (onVoiceStart) {
            onVoiceStart()
          }
        }
        voiceTimer = null
      }, vadConfig.voiceTimeout)
    }
  }

  /**
   * Lidar com silêncio
   */
  const handleSilence = (): void => {
    // Limpar timer de voz
    if (voiceTimer) {
      clearTimeout(voiceTimer)
      voiceTimer = null
    }

    // Se está falando, iniciar timer de silêncio
    if (isSpeaking.value && !silenceTimer) {
      silenceTimer = setTimeout(() => {
        if (isSpeaking.value) {
          console.log('🔇 [VAD] Silêncio detectado - parando gravação')
          isSpeaking.value = false
          if (onVoiceEnd) {
            onVoiceEnd()
          }
        }
        silenceTimer = null
      }, vadConfig.silenceTimeout)
    }
  }

  /**
   * Limpar todos os timers
   */
  const clearTimers = (): void => {
    if (silenceTimer) {
      clearTimeout(silenceTimer)
      silenceTimer = null
    }
    
    if (voiceTimer) {
      clearTimeout(voiceTimer)
      voiceTimer = null
    }
  }

  /**
   * Configurar callbacks
   */
  const setCallbacks = (callbacks: {
    onVoiceStart?: () => void
    onVoiceEnd?: () => void
    onVolumeChange?: (volume: number) => void
  }): void => {
    onVoiceStart = callbacks.onVoiceStart || null
    onVoiceEnd = callbacks.onVoiceEnd || null
    onVolumeChange = callbacks.onVolumeChange || null
  }

  /**
   * Atualizar configuração
   */
  const updateConfig = (newConfig: Partial<VADConfig>): void => {
    Object.assign(vadConfig, newConfig)
    console.log('⚙️ [VAD] Configuração atualizada:', vadConfig)
  }

  /**
   * Forçar início/fim da fala (para debugging)
   */
  const forceSpeaking = (speaking: boolean): void => {
    isSpeaking.value = speaking
    if (speaking && onVoiceStart) {
      onVoiceStart()
    } else if (!speaking && onVoiceEnd) {
      onVoiceEnd()
    }
  }

  return {
    // Estado
    vadState,
    isListening,
    isSpeaking,
    currentVolume,
    
    // Métodos
    startVAD,
    stopVAD,
    setCallbacks,
    updateConfig,
    forceSpeaking,
    
    // Config atual
    config: vadConfig
  }
} 