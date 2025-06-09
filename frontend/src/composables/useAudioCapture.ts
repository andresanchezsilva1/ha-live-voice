import { ref, onUnmounted } from 'vue'

export interface AudioCaptureConfig {
  channelCount?: number
  sampleRate?: number
  echoCancellation?: boolean
  noiseSuppression?: boolean
}

export interface AudioCaptureError {
  code: string
  message: string
  details?: string
}

// AudioWorklet source code baseado no script oficial do Google
const AUDIO_WORKLET_SOURCE = `
class AudioProcessingWorklet extends AudioWorkletProcessor {
  // Buffer de 2048 samples como no script oficial do Google
  // A 16kHz isso resulta em ~8 envios por segundo
  buffer = new Int16Array(2048);
  
  // Índice atual de escrita
  bufferWriteIndex = 0;
  
  constructor() {
    super();
    this.hasAudio = false;
  }
  
  /**
   * @param inputs Float32Array[][] [input#][channel#][sample#]
   * @param outputs Float32Array[][]
   */
  process(inputs) {
    if (inputs[0].length) {
      const channel0 = inputs[0][0];
      this.processChunk(channel0);
    }
    return true;
  }
  
  sendAndClearBuffer() {
    this.port.postMessage({
      event: "chunk",
      data: {
        int16arrayBuffer: this.buffer.slice(0, this.bufferWriteIndex).buffer,
      },
    });
    this.bufferWriteIndex = 0;
  }
  
  processChunk(float32Array) {
    const l = float32Array.length;
    
    for (let i = 0; i < l; i++) {
      // Converter float32 (-1 a 1) para int16 (-32768 a 32767)
      // Usando 32768 como no script oficial do Google
      const int16Value = float32Array[i] * 32768;
      this.buffer[this.bufferWriteIndex++] = int16Value;
      
      if(this.bufferWriteIndex >= this.buffer.length) {
        this.sendAndClearBuffer();
      }
    }
    
    if(this.bufferWriteIndex >= this.buffer.length) {
      this.sendAndClearBuffer();
    }
  }
}

registerProcessor('audio-recorder-worklet', AudioProcessingWorklet);
`;

export function useAudioCapture() {
  const isRecording = ref(false)
  const isConnecting = ref(false)
  const error = ref<AudioCaptureError | null>(null)
  const audioContext = ref<AudioContext | null>(null)
  const mediaStream = ref<MediaStream | null>(null)
  const audioWorkletNode = ref<AudioWorkletNode | null>(null)
  const websocket = ref<WebSocket | null>(null)
  const connectionRetryCount = ref(0)
  const isSharedWebSocket = ref(false) // Flag para indicar se o WebSocket é compartilhado
  
  const maxRetries = 3
  const retryDelay = 1000 // 1 segundo

  // Configuração padrão para captura de áudio
  const defaultConfig: AudioCaptureConfig = {
    channelCount: 1,
    sampleRate: 16000,
    echoCancellation: true,
    noiseSuppression: true
  }

  /**
   * Cria URL blob para o AudioWorklet
   */
  const createWorkletURL = (): string => {
    const blob = new Blob([AUDIO_WORKLET_SOURCE], { type: 'application/javascript' })
    return URL.createObjectURL(blob)
  }

  /**
   * Verifica se o navegador suporta as APIs necessárias
   */
  const checkBrowserSupport = (): boolean => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setError('BROWSER_NOT_SUPPORTED', 'Navegador não suporta captura de áudio')
      return false
    }

    if (!window.AudioContext && !(window as any).webkitAudioContext) {
      setError('AUDIO_CONTEXT_NOT_SUPPORTED', 'Navegador não suporta Web Audio API')
      return false
    }

    // Verificar suporte a AudioWorklet
    if (!AudioWorkletNode) {
      setError('AUDIO_WORKLET_NOT_SUPPORTED', 'Navegador não suporta AudioWorklet')
      return false
    }

    return true
  }

  /**
   * Solicita permissão para acessar o microfone
   */
  const requestMicrophonePermission = async (config: AudioCaptureConfig = defaultConfig): Promise<MediaStream> => {
    try {
      const constraints: MediaStreamConstraints = {
        audio: {
          channelCount: config.channelCount,
          sampleRate: config.sampleRate,
          echoCancellation: config.echoCancellation,
          noiseSuppression: config.noiseSuppression
        }
      }

      const stream = await navigator.mediaDevices.getUserMedia(constraints)
      return stream
    } catch (err: any) {
      console.error('Erro ao solicitar permissão do microfone:', err)
      
      switch (err.name) {
        case 'NotAllowedError':
          setError('PERMISSION_DENIED', 'Permissão de acesso ao microfone negada pelo usuário')
          break
        case 'NotFoundError':
          setError('NO_MICROPHONE', 'Nenhum microfone encontrado no dispositivo')
          break
        case 'NotReadableError':
          setError('MICROPHONE_IN_USE', 'Microfone já está sendo usado por outro aplicativo')
          break
        case 'OverconstrainedError':
          setError('CONSTRAINTS_NOT_SATISFIED', 'Configurações de áudio não suportadas pelo dispositivo')
          break
        default:
          setError('MICROPHONE_ACCESS_ERROR', `Erro ao acessar microfone: ${err.message}`)
      }
      
      throw err
    }
  }

  /**
   * Estabelece conexão WebSocket com retry automático
   */
  const connectWebSocket = async (wsUrl: string): Promise<WebSocket> => {
    return new Promise((resolve, reject) => {
      try {
        const ws = new WebSocket(wsUrl)
        
        const connectionTimeout = setTimeout(() => {
          ws.close()
          reject(new Error('Timeout na conexão WebSocket'))
        }, 10000) // 10 segundos de timeout

        ws.onopen = () => {
          clearTimeout(connectionTimeout)
          connectionRetryCount.value = 0
          console.log('WebSocket conectado com sucesso')
          resolve(ws)
        }

        ws.onerror = (err) => {
          clearTimeout(connectionTimeout)
          console.error('Erro no WebSocket:', err)
          reject(new Error('Falha na conexão WebSocket'))
        }

        ws.onclose = (event) => {
          clearTimeout(connectionTimeout)
          console.log('WebSocket fechado:', event.code, event.reason)
          
          // Se estava gravando e conexão foi perdida, tentar reconectar
          if (isRecording.value && connectionRetryCount.value < maxRetries) {
            setTimeout(() => {
              console.log(`Tentativa de reconexão ${connectionRetryCount.value + 1}/${maxRetries}`)
              connectionRetryCount.value++
              reconnectWebSocket(wsUrl)
            }, retryDelay * Math.pow(2, connectionRetryCount.value)) // Backoff exponencial
          }
        }
      } catch (err) {
        reject(err)
      }
    })
  }

  /**
   * Reconecta o WebSocket automaticamente
   */
  const reconnectWebSocket = async (wsUrl: string) => {
    try {
      websocket.value = await connectWebSocket(wsUrl)
    } catch (err) {
      console.error('Falha na reconexão:', err)
      if (connectionRetryCount.value >= maxRetries) {
        setError('WEBSOCKET_CONNECTION_FAILED', 'Falha na conexão com o servidor após múltiplas tentativas')
        stopRecording()
      }
    }
  }

  /**
   * Inicia a gravação de áudio
   */
  const startRecording = async (wsUrl: string | null, config: AudioCaptureConfig = defaultConfig, existingWebSocket?: WebSocket) => {
    try {
      // Evitar múltiplas tentativas simultâneas
      if (isConnecting.value || isRecording.value) {
        console.log('Já conectando ou gravando, ignorando nova tentativa')
        return
      }

      clearError()
      isConnecting.value = true

      // Garantir que qualquer conexão anterior foi fechada completamente
      if (websocket.value && websocket.value.readyState !== WebSocket.CLOSED) {
        console.log('Aguardando fechamento de conexão anterior...')
        await cleanup()
        // Aguardar um pouco mais para garantir que tudo foi limpo
        await new Promise(resolve => setTimeout(resolve, 200))
      }

      // Verificar suporte do navegador
      if (!checkBrowserSupport()) {
        isConnecting.value = false
        return
      }

      console.log('Iniciando gravação com configuração:', config)

      // Usar WebSocket existente ou estabelecer nova conexão
      if (existingWebSocket && existingWebSocket.readyState === WebSocket.OPEN) {
        console.log('🔌 Usando WebSocket existente')
        websocket.value = existingWebSocket
        isSharedWebSocket.value = true
      } else if (wsUrl && wsUrl.trim() !== '') {
        console.log('🔌 Estabelecendo nova conexão WebSocket:', wsUrl)
        websocket.value = await connectWebSocket(wsUrl)
        isSharedWebSocket.value = false
      } else {
        throw new Error('Nem WebSocket existente nem URL fornecida')
      }

      // Solicitar acesso ao microfone
      mediaStream.value = await requestMicrophonePermission(config)

      // Configurar Web Audio API
      const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext
      audioContext.value = new AudioContextClass({
        sampleRate: config.sampleRate || 16000
      })

      // Carregar AudioWorklet (baseado no script oficial do Google)
      const workletURL = createWorkletURL()
      try {
        await audioContext.value.audioWorklet.addModule(workletURL)
        console.log('🎵 [WORKLET] AudioWorklet carregado com sucesso')
      } catch (err) {
        console.error('❌ [WORKLET] Erro ao carregar AudioWorklet:', err)
        // Cleanup da URL
        URL.revokeObjectURL(workletURL)
        throw err
      }

      // Cleanup da URL após uso
      URL.revokeObjectURL(workletURL)

      // Criar nós de processamento de áudio
      const source = audioContext.value.createMediaStreamSource(mediaStream.value)
      audioWorkletNode.value = new AudioWorkletNode(audioContext.value, 'audio-recorder-worklet', {
        numberOfInputs: 1,
        numberOfOutputs: 1,
        outputChannelCount: [1],
        processorOptions: {
          numberOfInputs: 1,
          numberOfOutputs: 1,
          outputChannelCount: [1]
        }
      })

      // Conectar nós de áudio
      source.connect(audioWorkletNode.value)
      audioWorkletNode.value.connect(audioContext.value.destination)

              // Configurar handler para chunks de áudio do AudioWorklet
        audioWorkletNode.value.port.onmessage = (event: MessageEvent) => {
          if (!isRecording.value || !websocket.value || websocket.value.readyState !== WebSocket.OPEN) {
            return
          }

          // Processar eventos do AudioWorklet
          const { event: eventType, data } = event.data
          
          if (eventType === 'chunk' && data?.int16arrayBuffer) {
            try {
              const arrayBuffer = data.int16arrayBuffer
              websocket.value.send(arrayBuffer)
              
              // Log periódico (a cada ~2 segundos como no Google)
              if (Math.random() < 0.125) { // ~8 chunks/segundo, log 1 vez por segundo
                const int16View = new Int16Array(arrayBuffer)
                const maxValue = Math.max(...Array.from(int16View).map(Math.abs))
                console.log('🎤 [GOOGLE-STYLE] Enviando chunk para backend:', {
                  samples: int16View.length,
                  bytes: arrayBuffer.byteLength,
                  maxAmplitude: maxValue,
                  normalizedVolume: (maxValue / 32768).toFixed(4)
                })
              }
            } catch (error) {
              console.error('❌ [AUDIO-SEND] Erro ao enviar dados de áudio:', error)
            }
          }
        }

      isRecording.value = true
      isConnecting.value = false
      console.log('Gravação iniciada com sucesso')

    } catch (err: any) {
      console.error('Erro ao iniciar gravação:', err)
      isConnecting.value = false
      
      if (!error.value) { // Se o erro não foi definido pelas funções auxiliares
        setError('RECORDING_START_ERROR', `Erro ao iniciar gravação: ${err.message}`)
      }
      
      // Limpar recursos em caso de erro
      await cleanup()
      throw err
    }
  }

  /**
   * Para a gravação de áudio
   */
  const stopRecording = async () => {
    console.log('Parando gravação')
    
    // Parar imediatamente o processamento de áudio
    isRecording.value = false
    isConnecting.value = false
    
    // Cleanup imediato e ordenado
    await cleanup()
  }

  /**
   * Limpa todos os recursos
   */
  const cleanup = async () => {
    console.log('Iniciando cleanup de recursos de áudio')
    
    // 1. Parar o processador de áudio primeiro (para parar o envio)
    if (audioWorkletNode.value) {
      audioWorkletNode.value.port.onmessage = null // Remove o callback imediatamente
      audioWorkletNode.value.disconnect()
      audioWorkletNode.value = null
      console.log('AudioWorkletNode desconectado')
    }

    // 2. Parar as tracks de mídia
    if (mediaStream.value) {
      mediaStream.value.getTracks().forEach(track => {
        track.stop()
        console.log('Track de áudio parado:', track.label)
      })
      mediaStream.value = null
    }

    // 3. Fechar o AudioContext
    if (audioContext.value && audioContext.value.state !== 'closed') {
      try {
        await audioContext.value.close()
        console.log('AudioContext fechado')
      } catch (err) {
        console.warn('Erro ao fechar AudioContext:', err)
      }
      audioContext.value = null
    }

    // 4. Fechar WebSocket de forma síncrona (apenas se não for compartilhado)
    if (websocket.value && websocket.value.readyState !== WebSocket.CLOSED && !isSharedWebSocket.value) {
      console.log('Fechando conexão WebSocket...')
      
      // Criar promise para aguardar o fechamento
      await new Promise<void>((resolve) => {
        if (!websocket.value || websocket.value.readyState === WebSocket.CLOSED) {
          resolve()
          return
        }

        const currentWs = websocket.value
        let resolved = false
        
        // Listener para quando o WebSocket fechar
        const onClose = () => {
          if (!resolved) {
            resolved = true
            console.log('WebSocket fechado completamente')
            currentWs.removeEventListener('close', onClose)
            clearTimeout(timeoutId)
            resolve()
          }
        }
        
        currentWs.addEventListener('close', onClose)
        
        // Fechar o WebSocket
        currentWs.close(1000, 'User stopped recording')
        
        // Timeout de segurança (caso o close event não dispare)
        const timeoutId = setTimeout(() => {
          if (!resolved) {
            resolved = true
            currentWs.removeEventListener('close', onClose)
            console.log('WebSocket fechado por timeout')
            resolve()
          }
        }, 1000)
      })
    } else if (websocket.value && isSharedWebSocket.value) {
      console.log('WebSocket compartilhado, apenas desconectando do processamento de áudio')
    }
    
    websocket.value = null
    isSharedWebSocket.value = false

    connectionRetryCount.value = 0
    console.log('Cleanup concluído')
  }

  /**
   * Converte Float32Array para Int16Array para formato PCM
   */
  const convertFloat32ToInt16 = (buffer: Float32Array): ArrayBuffer => {
    const l = buffer.length
    const buf = new Int16Array(l)

    for (let i = 0; i < l; i++) {
      // Clamping e scaling para Int16
      const sample = Math.min(1, Math.max(-1, buffer[i]))
      buf[i] = sample * 0x7FFF
    }

    return buf.buffer
  }

  /**
   * Define um erro
   */
  const setError = (code: string, message: string, details?: string) => {
    error.value = { code, message, details }
  }

  /**
   * Limpa o erro atual
   */
  const clearError = () => {
    error.value = null
  }

  /**
   * Obtém informações sobre dispositivos de áudio disponíveis
   */
  const getAudioDevices = async () => {
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
        throw new Error('enumerateDevices não suportado')
      }

      const devices = await navigator.mediaDevices.enumerateDevices()
      return devices.filter(device => device.kind === 'audioinput')
    } catch (err: any) {
      console.error('Erro ao listar dispositivos de áudio:', err)
      setError('DEVICE_ENUMERATION_ERROR', `Erro ao listar dispositivos: ${err.message}`)
      return []
    }
  }

  // Limpar recursos ao desmontar o componente
  onUnmounted(async () => {
    console.log('Componente desmontado, limpando recursos de áudio')
    await stopRecording()
  })

  return {
    // Estados reativos
    isRecording,
    isConnecting,
    error,
    mediaStream,
    
    // Métodos principais
    startRecording,
    stopRecording,
    clearError,
    getAudioDevices,
    
    // Utilitários
    checkBrowserSupport
  }
} 