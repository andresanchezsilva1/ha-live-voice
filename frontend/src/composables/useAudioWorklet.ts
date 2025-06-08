/**
 * Audio Worklet-based Voice Activity Detection
 * Baseado no padrão oficial do Google
 */

import { ref, computed } from 'vue'
import { useSharedAudioContext } from './useSharedAudioContext'

export interface AudioWorkletConfig {
  volumeThreshold: number
  silenceTimeout: number
  voiceTimeout: number
  sampleRate: number
}

export interface AudioWorkletState {
  isListening: boolean
  isSpeaking: boolean
  volume: number
  isRecording: boolean
}

export function useAudioWorklet(config: Partial<AudioWorkletConfig> = {}) {
  const { getAudioContext, ensureAudioContextReady } = useSharedAudioContext()
  
  // Configuração padrão
  const workletConfig: AudioWorkletConfig = {
    volumeThreshold: 0.01,
    silenceTimeout: 2500,
    voiceTimeout: 300,
    sampleRate: 16000,
    ...config
  }

  // Estado
  const isListening = ref(false)
  const isSpeaking = ref(false)
  const currentVolume = ref(0)
  const isRecording = ref(false)

  // Recursos
  let stream: MediaStream | null = null
  let audioContext: AudioContext | null = null
  let source: MediaStreamAudioSourceNode | null = null
  let volumeWorklet: AudioWorkletNode | null = null
  
  // Timers
  let silenceTimer: number | null = null
  let voiceTimer: number | null = null

  // Callbacks
  let onVoiceStart: (() => void) | null = null
  let onVoiceEnd: (() => void) | null = null
  let onVolumeChange: ((volume: number) => void) | null = null

  // Estado computado
  const workletState = computed<AudioWorkletState>(() => ({
    isListening: isListening.value,
    isSpeaking: isSpeaking.value,
    volume: currentVolume.value,
    isRecording: isRecording.value
  }))

  /**
   * Criar o código do worklet inline
   */
  const createVolumeWorkletCode = () => {
    return `
      class VolumeProcessor extends AudioWorkletProcessor {
        constructor(options) {
          super()
          this.volumeThreshold = options.processorOptions.volumeThreshold || 0.01
          this.silenceTimeout = options.processorOptions.silenceTimeout || 2500
          this.voiceTimeout = options.processorOptions.voiceTimeout || 300
          
          this.lastVoiceTime = 0
          this.isSpeaking = false
          this.silenceStart = 0
          this.voiceStart = 0
        }

        process(inputs, outputs, parameters) {
          const input = inputs[0]
          if (!input || !input[0]) return true

          // Calcular volume RMS
          const samples = input[0]
          let sum = 0
          for (let i = 0; i < samples.length; i++) {
            sum += samples[i] * samples[i]
          }
          const rms = Math.sqrt(sum / samples.length)
          const volume = Math.min(1.0, rms * 10) // Amplificar para melhor detecção

                     // Enviar volume para o thread principal
           this.port.postMessage({
             type: 'volume',
             volume: volume,
             timestamp: Date.now()
           })

          // Detectar atividade de voz
          const currentTime = Date.now()
          
          if (volume > this.volumeThreshold) {
            if (!this.isSpeaking) {
              if (this.voiceStart === 0) {
                this.voiceStart = currentTime
              } else if (currentTime - this.voiceStart >= this.voiceTimeout) {
                this.isSpeaking = true
                this.port.postMessage({
                  type: 'voiceStart',
                  timestamp: currentTime
                })
                this.voiceStart = 0
              }
            }
            this.lastVoiceTime = currentTime
            this.silenceStart = 0
          } else {
            this.voiceStart = 0
            if (this.isSpeaking) {
              if (this.silenceStart === 0) {
                this.silenceStart = currentTime
              } else if (currentTime - this.silenceStart >= this.silenceTimeout) {
                this.isSpeaking = false
                this.port.postMessage({
                  type: 'voiceEnd',
                  timestamp: currentTime
                })
                this.silenceStart = 0
              }
            }
          }

          return true
        }
      }

      registerProcessor('volume-processor', VolumeProcessor)
    `
  }

  /**
   * Inicializar o worklet
   */
  const startWorklet = async (): Promise<void> => {
    try {
      console.log('🎤 [WORKLET] Iniciando AudioWorklet-based VAD...')
      
      // Obter AudioContext compartilhado
      audioContext = await getAudioContext()
      await ensureAudioContextReady()

      // Solicitar acesso ao microfone
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          sampleRate: workletConfig.sampleRate
        }
      })

      // Criar fonte de áudio
      source = audioContext.createMediaStreamSource(stream)

      // Criar e adicionar o worklet
      const workletCode = createVolumeWorkletCode()
      const workletBlob = new Blob([workletCode], { type: 'application/javascript' })
      const workletUrl = URL.createObjectURL(workletBlob)
      
      await audioContext.audioWorklet.addModule(workletUrl)
      
      // Criar nó do worklet
      volumeWorklet = new AudioWorkletNode(audioContext, 'volume-processor', {
        processorOptions: {
          volumeThreshold: workletConfig.volumeThreshold,
          silenceTimeout: workletConfig.silenceTimeout,
          voiceTimeout: workletConfig.voiceTimeout
        }
      })

      // Configurar handlers de mensagens
      volumeWorklet.port.onmessage = handleWorkletMessage

      // Conectar o pipeline
      source.connect(volumeWorklet)
      
      // Limpar URL do blob
      URL.revokeObjectURL(workletUrl)
      
      isListening.value = true
      
      console.log('✅ [WORKLET] AudioWorklet VAD iniciado com sucesso')
    } catch (error) {
      console.error('❌ [WORKLET] Erro ao iniciar AudioWorklet VAD:', error)
      throw error
    }
  }

  /**
   * Parar o worklet
   */
  const stopWorklet = (): void => {
    try {
      console.log('🛑 [WORKLET] Parando AudioWorklet VAD...')
      
      // Limpar timers
      clearTimers()
      
      // Desconectar e limpar recursos
      if (volumeWorklet) {
        volumeWorklet.disconnect()
        volumeWorklet = null
      }
      
      if (source) {
        source.disconnect()
        source = null
      }
      
      if (stream) {
        stream.getTracks().forEach(track => track.stop())
        stream = null
      }
      
      // Resetar estado
      isListening.value = false
      isSpeaking.value = false
      currentVolume.value = 0
      isRecording.value = false
      
      console.log('✅ [WORKLET] AudioWorklet VAD parado')
    } catch (error) {
      console.error('❌ [WORKLET] Erro ao parar AudioWorklet VAD:', error)
    }
  }

  /**
   * Handler para mensagens do worklet
   */
  const handleWorkletMessage = (event: MessageEvent) => {
    const { type, volume, timestamp } = event.data
    
    switch (type) {
      case 'volume':
        currentVolume.value = volume
        if (onVolumeChange) {
          onVolumeChange(volume)
        }
        break
        
      case 'voiceStart':
        console.log('🎤 [WORKLET] Voz detectada')
        isSpeaking.value = true
        if (onVoiceStart) {
          onVoiceStart()
        }
        break
        
      case 'voiceEnd':
        console.log('🔇 [WORKLET] Fim da voz detectado')
        isSpeaking.value = false
        if (onVoiceEnd) {
          onVoiceEnd()
        }
        break
    }
  }

  /**
   * Limpar timers
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
  const updateConfig = (newConfig: Partial<AudioWorkletConfig>): void => {
    Object.assign(workletConfig, newConfig)
    console.log('⚙️ [WORKLET] Configuração atualizada:', workletConfig)
  }

  /**
   * Forçar estado de fala (para debugging)
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
    workletState,
    isListening,
    isSpeaking,
    currentVolume,
    
    // Métodos
    startWorklet,
    stopWorklet,
    setCallbacks,
    updateConfig,
    forceSpeaking,
    
    // Config atual
    config: workletConfig
  }
} 