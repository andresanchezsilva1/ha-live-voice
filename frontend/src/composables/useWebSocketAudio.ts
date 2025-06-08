import { ref, onUnmounted, watch, readonly } from 'vue'
import { useAppStore } from '../store/appStore'
import { useAudioCapture } from './useAudioCapture'
import { useAudioPlayback } from './useAudioPlayback'
import { AudioStreamer, useAudioStreamer } from './useAudioStreamer'
import { useSharedAudioContext } from './useSharedAudioContext'

export interface WebSocketMessage {
  type: 'audio' | 'audio_response' | 'audio_chunk' | 'audio_complete' | 'transcription' | 'response' | 'error' | 'status' | 'connection_established' | 'audio_received'
  data?: any
  content?: string
  timestamp?: number
  has_audio?: boolean
  session_id?: string
  // Audio streaming properties
  size?: number
  format?: string
  streaming?: boolean
  chunks_sent?: number
  total_size?: number
  // PCM streaming properties
  sample_rate?: number
  channels?: number
  bits_per_sample?: number
  chunk_id?: string
  buffer_size?: number
}

export function useWebSocketAudio(wsUrl: string) {
  const store = useAppStore()
  const { getAudioContext, ensureAudioContextReady } = useSharedAudioContext()
  const { startRecording, stopRecording, isRecording, error: captureError } = useAudioCapture()
  const { 
    enqueueAudio, 
    setVolume, 
    toggleMute, 
    clearQueue,
    prepareAudioContext,
    state: playbackState 
  } = useAudioPlayback()
  
  const websocket = ref<WebSocket | null>(null)
  const reconnectAttempts = ref(0)
  const maxReconnectAttempts = 3
  const isConnecting = ref(false)
  const lastMessageTimestamp = ref(Date.now())
  
  // PCM streaming management usando AudioStreamer
  const currentStreamMetadata = ref<any>(null)
  const isStreamingActive = ref(false)
  const currentResponseId = ref<string | null>(null)
  let audioStreamer: AudioStreamer | null = null
  
  // Chunk deduplication
  const processedChunks = new Set<string>()

  /**
   * Initialize/Reinitialize AudioStreamer for new stream
   */
  const initializeAudioStreamerForNewStream = async (sampleRate: number = 24000): Promise<void> => {
    try {
      console.log(`🔄 [STREAM-INIT] Inicializando AudioStreamer para novo stream com ${sampleRate}Hz...`)
      
      // Parar e limpar AudioStreamer anterior se existir
      if (audioStreamer) {
        console.log('🛑 [STREAM-INIT] Parando AudioStreamer anterior')
        audioStreamer.stop()
        audioStreamer = null
      }
      
      // Garantir que o AudioContext está pronto
      const audioContext = await getAudioContext()
      await ensureAudioContextReady()
      
      // Criar novo AudioStreamer com sample rate correto
      audioStreamer = new AudioStreamer(audioContext, sampleRate)
      
      // Configurar callbacks
      audioStreamer.onComplete = () => {
        console.log('🎵 [STREAMER-COMPLETE] Reprodução do stream finalizada')
        // Não modificar diretamente playbackState.isPlaying, será gerenciado pelo useAudioPlayback
        store.addNotification('status', 'Reprodução de áudio finalizada')
      }
      
      audioStreamer.onError = (error: Error) => {
        console.error('❌ [STREAMER-ERROR] Erro no AudioStreamer:', error)
        // Não modificar diretamente playbackState.isPlaying, será gerenciado pelo useAudioPlayback
        store.setError('AUDIO_STREAMING_ERROR', 'Erro no streaming de áudio', error.message)
      }
      
      // Aplicar configurações atuais
      audioStreamer.setVolume(playbackState.volume)
      
      console.log(`✅ [STREAM-INIT] Novo AudioStreamer criado e configurado com ${sampleRate}Hz`)
      
    } catch (error) {
      console.error('❌ [STREAM-INIT] Erro ao inicializar AudioStreamer:', error)
      throw error
    }
  }

  /**
   * Process PCM chunk using AudioStreamer
   */
  const processPCMChunk = async (pcmData: ArrayBuffer, metadata: any): Promise<void> => {
    try {
      const chunkId = Date.now() + Math.random().toString(36).substr(2, 9)
      
      // Create chunk fingerprint for deduplication
      const chunk = new Uint8Array(pcmData)
      const firstBytes = Array.from(chunk.slice(0, 16)).map(b => b.toString(16).padStart(2, '0')).join('')
      const chunkFingerprint = `${pcmData.byteLength}_${firstBytes}`
      
      // Check for duplicate chunks
      if (processedChunks.has(chunkFingerprint)) {
        console.log(`⚠️ [DEDUP] Chunk duplicado detectado e ignorado: ${chunkFingerprint}`)
        return
      }
      
      // Add to processed chunks (keep only last 100 to prevent memory leak)
      processedChunks.add(chunkFingerprint)
      if (processedChunks.size > 100) {
        const firstItem = processedChunks.values().next().value
        if (firstItem) {
          processedChunks.delete(firstItem)
        }
      }
      
      console.log('🎵 [PCM-STREAM] Processando chunk PCM com AudioStreamer:', {
        chunkId,
        size: pcmData.byteLength,
        format: metadata?.format,
        sampleRate: metadata?.sample_rate,
        streamingActive: isStreamingActive.value,
        fingerprint: chunkFingerprint,
        timestamp: new Date().toISOString()
      })
      
      // AudioStreamer should already be initialized by audio_chunk handler
      if (!audioStreamer) {
        console.warn('⚠️ [PCM-STREAM] AudioStreamer não encontrado, pulando chunk')
        return
      }
      
      // Store metadata from first chunk
      if (!currentStreamMetadata.value && metadata) {
        currentStreamMetadata.value = metadata
        isStreamingActive.value = true
        console.log('🎵 [PCM-STREAM] Iniciando stream com metadata:', metadata)
      }
      
      if (audioStreamer) {
        // Convert ArrayBuffer to Uint8Array and send to streamer
        const chunk = new Uint8Array(pcmData)
        
        // Add debug info about the chunk content (first few bytes)
        const firstBytes = Array.from(chunk.slice(0, 8)).map(b => b.toString(16).padStart(2, '0')).join(' ')
        console.log(`🎵 [PCM-DEBUG] Chunk ${chunkId} primeiros bytes: ${firstBytes}`)
        
        // Send directly to AudioStreamer
        audioStreamer.addPCM16(chunk)
        
        console.log(`✅ [PCM-STREAM] Chunk ${chunkId} enviado para AudioStreamer`)
      } else {
        console.error('❌ [PCM-STREAM] AudioStreamer não disponível')
      }
      
    } catch (error) {
      console.error('❌ [PCM-STREAM] Erro ao processar chunk PCM:', error)
    }
  }

  /**
   * Finalize PCM streaming 
   */
  const finalizePCMStream = (): void => {
    try {
      console.log('🎵 [PCM-STREAM] Iniciando finalização do stream:', {
        hasStreamer: !!audioStreamer,
        hasMetadata: !!currentStreamMetadata.value,
        isActive: isStreamingActive.value
      })
      
      if (audioStreamer) {
        audioStreamer.complete()
        console.log('🎵 [STREAMER] Stream marcado como completo')
      }
      
      // Reset streaming state
      currentStreamMetadata.value = null
      isStreamingActive.value = false
      currentResponseId.value = null
      
      console.log('✅ [PCM-STREAM] Stream finalizado - estado resetado')
      
    } catch (error) {
      console.error('❌ [PCM-STREAM] Erro ao finalizar stream:', error)
      // Force reset state even on error
      currentStreamMetadata.value = null
      isStreamingActive.value = false
      currentResponseId.value = null
    }
  }

  // Sincronizar estados dos composables com a store
  watch(isRecording, (recording) => {
    store.setRecordingStatus(recording)
  })

  watch(() => playbackState.isPlaying, (playing) => {
    store.setPlayingStatus(playing)
  })

  watch(() => playbackState.volume, (volume) => {
    store.setVolume(volume)
    // Sync volume with AudioStreamer
    if (audioStreamer) {
      audioStreamer.setVolume(volume)
    }
  })

  watch(() => playbackState.isMuted, (muted) => {
    if (muted) {
      store.toggleMute()
      if (audioStreamer) {
        audioStreamer.setVolume(0)
      }
    } else if (audioStreamer) {
      audioStreamer.setVolume(playbackState.volume)
    }
  })

  watch(captureError, (error) => {
    if (error) {
      store.setError(error.code, error.message, error.details)
    }
  })

  /**
   * Conecta ao WebSocket
   */
  const connect = async (): Promise<void> => {
    if (isConnecting.value || (websocket.value && websocket.value.readyState === WebSocket.CONNECTING)) {
      console.log('⏳ Já conectando, aguardando...')
      return
    }

    if (websocket.value && websocket.value.readyState === WebSocket.OPEN) {
      console.log('✅ WebSocket já conectado')
      return
    }

    try {
      isConnecting.value = true
      store.setConnectingStatus(true)
      store.clearError()

      console.log('🔌 Conectando WebSocket:', wsUrl)

      websocket.value = new WebSocket(wsUrl)

      // Timeout para conexão
      const connectionTimeout = setTimeout(() => {
        if (websocket.value && websocket.value.readyState !== WebSocket.OPEN) {
          websocket.value.close()
          throw new Error('Timeout na conexão WebSocket')
        }
      }, 10000)

      websocket.value.onopen = async () => {
        clearTimeout(connectionTimeout)
        isConnecting.value = false
        store.setConnectingStatus(false)
        store.setConnectionStatus(true)
        reconnectAttempts.value = 0
        lastMessageTimestamp.value = Date.now()
        
        console.log('✅ WebSocket conectado com sucesso')
        store.addNotification('status', 'Conectado ao servidor com sucesso!')
        
        // Reset PCM streaming state for new connection
        currentStreamMetadata.value = null
        isStreamingActive.value = false
        
        // Clear chunk deduplication cache
        processedChunks.clear()
        
        // Destroy old streamer and prepare for new one
        if (audioStreamer) {
          audioStreamer.stop()
          audioStreamer = null
        }
        console.log('🎵 [RESET] Estado PCM resetado para nova conexão')
        
        // Preparar AudioContext após conexão (interação do usuário)
        try {
          console.log('🎵 [INIT] Preparando AudioContext após conexão...')
          await prepareAudioContext()
          console.log('✅ [INIT] AudioContext preparado com sucesso')
        } catch (error) {
          console.warn('⚠️ [INIT] Aviso: AudioContext não pôde ser preparado automaticamente:', error)
          store.addNotification('status', 'AudioContext será preparado quando o primeiro áudio for reproduzido')
        }
        
        // Enviar mensagem de inicialização
        sendMessage({
          type: 'status',
          content: 'client_connected',
          timestamp: Date.now()
        })
      }

      websocket.value.onerror = (error) => {
        console.error('❌ WebSocket error:', error)
        clearTimeout(connectionTimeout)
        isConnecting.value = false
        store.setConnectingStatus(false)
        store.setConnectionStatus(false)
        store.setError('WEBSOCKET_ERROR', 'Erro na conexão WebSocket', (error as Event).toString())
      }

      websocket.value.onclose = (event) => {
        console.log('🔌 WebSocket fechado:', event.code, event.reason)
        isConnecting.value = false
        store.setConnectingStatus(false)
        store.setConnectionStatus(false)

        // Reset streaming state
        currentStreamMetadata.value = null
        isStreamingActive.value = false
        if (audioStreamer) {
          audioStreamer.stop()
          audioStreamer = null
        }

        if (event.code !== 1000 && reconnectAttempts.value < maxReconnectAttempts) {
          const delay = Math.pow(2, reconnectAttempts.value) * 1000
          console.log(`🔄 Tentando reconectar em ${delay}ms (tentativa ${reconnectAttempts.value + 1}/${maxReconnectAttempts})`)
          
          setTimeout(() => {
            reconnectAttempts.value++
            connect()
          }, delay)
        } else if (reconnectAttempts.value >= maxReconnectAttempts) {
          store.setError('WEBSOCKET_ERROR', 'Falha na reconexão', `Esgotadas ${maxReconnectAttempts} tentativas de reconexão`)
        }
      }

      websocket.value.onmessage = handleWebSocketMessage

    } catch (error) {
      console.error('❌ Erro ao conectar WebSocket:', error)
      isConnecting.value = false
      store.setConnectingStatus(false)
      store.setError('WEBSOCKET_ERROR', 'Falha na conexão WebSocket', (error as Error).toString())
      throw error
    }
  }

  /**
   * Desconecta do WebSocket
   */
  const disconnect = (): void => {
    if (websocket.value) {
      websocket.value.close()
      websocket.value = null
    }
    
    // Reset PCM streaming state
    currentStreamMetadata.value = null
    isStreamingActive.value = false
    if (audioStreamer) {
      audioStreamer.stop()
      audioStreamer = null
    }
    console.log('🎵 [DISCONNECT] Estado PCM resetado')
    
    isConnecting.value = false
    store.setConnectingStatus(false)
    store.setConnectionStatus(false)
    
    console.log('🔌 WebSocket desconectado')
  }

  /**
   * Envia mensagem via WebSocket
   */
  const sendMessage = (message: any): void => {
    if (websocket.value && websocket.value.readyState === WebSocket.OPEN) {
      websocket.value.send(JSON.stringify(message))
      lastMessageTimestamp.value = Date.now()
    } else {
      console.warn('⚠️ WebSocket não está conectado, não é possível enviar mensagem')
    }
  }

  /**
   * Envia audio via WebSocket
   */
  const sendAudio = (audioData: ArrayBuffer): void => {
    if (websocket.value && websocket.value.readyState === WebSocket.OPEN) {
      websocket.value.send(audioData)
      lastMessageTimestamp.value = Date.now()
    } else {
      console.warn('⚠️ WebSocket não está conectado, não é possível enviar áudio')
    }
  }

  /**
   * Processa mensagens recebidas do WebSocket
   */
  const handleWebSocketMessage = async (event: MessageEvent) => {
    lastMessageTimestamp.value = Date.now()
    
    try {
      // Handle JSON messages
      if (typeof event.data === 'string') {
        const message: WebSocketMessage = JSON.parse(event.data)
        
        console.log('📨 Mensagem recebida:', {
          type: message.type,
          hasContent: !!message.content,
          hasData: !!message.data,
          timestamp: message.timestamp
        })

        switch (message.type) {
          case 'transcription':
            if (message.content) {
              store.addMessage('transcription', message.content)
              console.log('✍️ Transcrição:', message.content)
            }
            break

          case 'response':
            console.log('🤖 Resposta:', message.content)
            if (message.content) {
              store.addMessage('response', message.content)
            }
            
            // A resposta de texto indica o início de uma nova resposta do assistente
            // Marcar que devemos preparar para novo stream de áudio
            const responseId = message.timestamp?.toString() || Date.now().toString()
            if (currentResponseId.value !== responseId) {
              console.log('🆕 [NEW-RESPONSE] Nova resposta detectada, preparando para novo stream:', responseId)
              currentResponseId.value = responseId
              // Reset streaming state for new response
              currentStreamMetadata.value = null
              isStreamingActive.value = false
              // AudioStreamer será inicializado quando o primeiro audio_chunk chegar
            }
            break

          case 'audio_chunk':
            console.log('🎵 [AUDIO-CHUNK] Metadata recebido:', {
              size: message.size,
              format: message.format,
              streaming: message.streaming,
              chunks_sent: message.chunks_sent,
              sample_rate: message.sample_rate,
              chunk_id: message.chunk_id
            })
            
            // Só inicializar AudioStreamer se não temos um stream ativo OU se há mudança significativa no sample rate
            const needsNewStreamer = !isStreamingActive.value || 
                                   !audioStreamer || 
                                   (currentStreamMetadata.value && 
                                    currentStreamMetadata.value.sample_rate !== message.sample_rate)
            
            if (needsNewStreamer) {
              console.log('🔄 [NEW-STREAM] Inicializando AudioStreamer - necessário novo streamer')
              await initializeAudioStreamerForNewStream(message.sample_rate || 24000)
            } else {
              console.log('📨 [SAME-STREAM] Continuando stream existente')
            }
            
            // Store metadata for incoming audio chunks
            currentStreamMetadata.value = {
              format: message.format,
              sample_rate: message.sample_rate,
              channels: message.channels,
              bits_per_sample: message.bits_per_sample,
              streaming: message.streaming
            }
            isStreamingActive.value = true
            break

          case 'audio_complete':
            console.log('🎵 [AUDIO-COMPLETE] Stream finalizado')
            finalizePCMStream()
            // Reset response tracking when stream completes
            currentResponseId.value = null
            // Notificar que o áudio terminou para permitir reativação do VAD
            store.addNotification('status', 'Reprodução de áudio finalizada')
            break

          case 'connection_established':
            console.log('✅ Conexão WebSocket estabelecida com sucesso')
            store.addNotification('status', 'Conexão estabelecida')
            break

          case 'error':
            console.error('❌ Erro do servidor:', message.content)
            store.setError('SERVER_ERROR', 'Erro do servidor', message.content || 'Erro desconhecido do servidor')
            break

          case 'status':
            console.log('📊 Status:', message.content)
            store.addNotification('status', message.content || 'Status atualizado')
            break

          case 'audio_received':
            // Mensagem de status do backend sobre buffer de áudio
            console.log('📊 [AUDIO-STATUS] Buffer no servidor:', {
              buffer_size: message.buffer_size,
              timestamp: message.timestamp
            })
            break

          default:
            console.log('⚠️ Tipo de mensagem desconhecido:', message.type)
        }
      }
      // Handle binary data (PCM chunks)
      else if (event.data instanceof ArrayBuffer) {
        console.log('🎵 [BINARY] Chunk PCM recebido:', {
          size: event.data.byteLength,
          hasMetadata: !!currentStreamMetadata.value,
          isStreaming: isStreamingActive.value
        })
        
        if (currentStreamMetadata.value) {
          processPCMChunk(event.data, currentStreamMetadata.value).catch(error => {
            console.error('❌ [BINARY] Erro ao processar chunk PCM:', error)
          })
        } else {
          console.warn('⚠️ [BINARY] Chunk PCM recebido sem metadata, ignorando')
        }
      }
      // Handle Blob data
      else if (event.data instanceof Blob) {
        console.log('🎵 [BLOB] Chunk recebido como Blob:', {
          size: event.data.size,
          type: event.data.type
        })
        
        const arrayBuffer = await event.data.arrayBuffer()
        if (currentStreamMetadata.value) {
          processPCMChunk(arrayBuffer, currentStreamMetadata.value).catch(error => {
            console.error('❌ [BLOB] Erro ao processar chunk PCM:', error)
          })
        } else {
          console.warn('⚠️ [BLOB] Chunk recebido sem metadata, ignorando')
        }
      }
      else {
        console.warn('⚠️ Tipo de dados desconhecido:', typeof event.data)
      }
    } catch (error) {
      console.error('❌ Erro ao processar mensagem WebSocket:', error)
      store.setError('WEBSOCKET_MESSAGE_ERROR', 'Erro ao processar mensagem', (error as Error).toString())
    }
  }

  /**
   * Inicia gravação de áudio
   */
  const startAudioRecording = async (): Promise<void> => {
    try {
      console.log('🎤 Iniciando gravação...')
      
      // Verificar se já está conectado
      if (!websocket.value || websocket.value.readyState !== WebSocket.OPEN) {
        console.log('⚠️ WebSocket não conectado, conectando primeiro...')
        await connect()
      }
      
      // Verificar novamente se a conexão foi estabelecida
      if (!websocket.value || websocket.value.readyState !== WebSocket.OPEN) {
        throw new Error('Não foi possível estabelecer conexão WebSocket')
      }
      
      // Aguardar um pouco para garantir que a inicialização foi processada
      await new Promise(resolve => setTimeout(resolve, 100))
      
      // Usar o useAudioCapture com a conexão WebSocket existente
      await startRecording('', {
        channelCount: 1,
        sampleRate: 16000,
        echoCancellation: true,
        noiseSuppression: true
      }, websocket.value)
      
      store.addNotification('status', 'Gravação iniciada')
    } catch (error) {
      console.error('❌ Erro ao iniciar gravação:', error)
      store.setError('RECORDING_ERROR', 'Erro ao iniciar gravação', (error as Error).toString())
      throw error
    }
  }

  /**
   * Para gravação de áudio
   */
  const stopAudioRecording = (): void => {
    try {
      console.log('🎤 Parando gravação...')
      stopRecording()
      store.addNotification('status', 'Gravação finalizada')
    } catch (error) {
      console.error('❌ Erro ao parar gravação:', error)
      store.setError('RECORDING_ERROR', 'Erro ao parar gravação', (error as Error).toString())
    }
  }

  /**
   * Para tudo e limpa recursos
   */
  const cleanup = (): void => {
    try {
      disconnect()
      stopRecording()
      clearQueue()
      if (audioStreamer) {
        audioStreamer.stop()
        audioStreamer = null
      }
      currentStreamMetadata.value = null
      isStreamingActive.value = false
      currentResponseId.value = null
      
      // Clear chunk deduplication cache
      processedChunks.clear()
      
      console.log('🧹 Cleanup completo')
    } catch (error) {
      console.error('❌ Erro durante cleanup:', error)
    }
  }

  // Return the interface
  return {
    // Connection state
    websocket: readonly(websocket),
    isConnecting: readonly(isConnecting),
    
    // Audio streaming state
    isStreamingActive: readonly(isStreamingActive),
    currentStreamMetadata: readonly(currentStreamMetadata),
    
    // Connection methods
    connect,
    disconnect,
    
    // Communication methods
    sendMessage,
    sendAudio,
    
    // Audio methods
    startAudioRecording,
    stopAudioRecording,
    
    // Audio playback controls (passthrough)
    setVolume,
    toggleMute,
    clearQueue,
    
    // State
    isRecording: readonly(isRecording),
    playbackState: readonly(playbackState),
    captureError: readonly(captureError),
    
    // Cleanup
    cleanup
  }
} 