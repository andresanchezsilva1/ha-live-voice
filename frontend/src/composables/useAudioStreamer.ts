/**
 * Audio Streamer baseado no exemplo do Google
 * Para streaming contínuo de chunks PCM raw
 */

export class AudioStreamer {
  private sampleRate: number
  private bufferSize: number = 7680
  private audioQueue: Float32Array[] = []
  private isPlaying: boolean = false
  private isStreamComplete: boolean = false
  private checkInterval: number | null = null
  private scheduledTime: number = 0
  private initialBufferTime: number = 0.1 // 100ms buffer inicial
  
  public gainNode: GainNode
  public source: AudioBufferSourceNode
  private endOfQueueAudioSource: AudioBufferSourceNode | null = null
  
  public onComplete = () => {}
  public onError = (error: Error) => {}

  constructor(public context: AudioContext, sampleRate: number = 24000) {
    this.sampleRate = sampleRate
    console.log(`🎵 [STREAMER] Inicializando AudioStreamer com sample rate: ${this.sampleRate}Hz`)
    this.gainNode = this.context.createGain()
    this.source = this.context.createBufferSource()
    this.gainNode.connect(this.context.destination)
    this.addPCM16 = this.addPCM16.bind(this)
  }

  /**
   * Converte Uint8Array de PCM16 para Float32Array
   * PCM16 é formato raw, mas Web Audio API espera Float32Array normalizado entre -1.0 e 1.0
   */
  private _processPCM16Chunk(chunk: Uint8Array): Float32Array {
    const float32Array = new Float32Array(chunk.length / 2)
    const dataView = new DataView(chunk.buffer)

    for (let i = 0; i < chunk.length / 2; i++) {
      try {
        const int16 = dataView.getInt16(i * 2, true) // little-endian
        float32Array[i] = int16 / 32768 // normalizar para -1.0 a 1.0
      } catch (e) {
        console.error('Erro ao processar chunk PCM:', e)
        this.onError(e as Error)
      }
    }
    return float32Array
  }

  /**
   * Adiciona chunk PCM16 raw para reprodução
   */
  addPCM16(chunk: Uint8Array) {
    console.log(`🎵 [STREAMER] Recebendo chunk PCM: ${chunk.length} bytes`)
    
    // Reset flag de stream completo quando novo chunk chega
    this.isStreamComplete = false
    
    // Processar chunk para Float32Array
    let processingBuffer = this._processPCM16Chunk(chunk)
    
    // Dividir em buffers do tamanho adequado
    while (processingBuffer.length >= this.bufferSize) {
      const buffer = processingBuffer.slice(0, this.bufferSize)
      this.audioQueue.push(buffer)
      processingBuffer = processingBuffer.slice(this.bufferSize)
      console.log(`🎵 [STREAMER] Buffer adicionado à fila: ${buffer.length} samples`)
    }
    
    // Adicionar buffer restante se não estiver vazio
    if (processingBuffer.length > 0) {
      this.audioQueue.push(processingBuffer)
      console.log(`🎵 [STREAMER] Buffer final adicionado: ${processingBuffer.length} samples`)
    }
    
    // Iniciar reprodução se não estiver tocando
    if (!this.isPlaying) {
      console.log('🎵 [STREAMER] Iniciando reprodução')
      this.isPlaying = true
      // Inicializar scheduledTime apenas quando começamos a tocar
      this.scheduledTime = this.context.currentTime + this.initialBufferTime
      this.scheduleNextBuffer()
    }
  }

  private createAudioBuffer(audioData: Float32Array): AudioBuffer {
    const audioBuffer = this.context.createBuffer(
      1, // mono
      audioData.length,
      this.sampleRate
    )
    audioBuffer.getChannelData(0).set(audioData)
    return audioBuffer
  }

  private scheduleNextBuffer() {
    const SCHEDULE_AHEAD_TIME = 0.2

    while (
      this.audioQueue.length > 0 &&
      this.scheduledTime < this.context.currentTime + SCHEDULE_AHEAD_TIME
    ) {
      const audioData = this.audioQueue.shift()!
      const audioBuffer = this.createAudioBuffer(audioData)
      const source = this.context.createBufferSource()

      // Detectar último buffer na fila
      if (this.audioQueue.length === 0) {
        if (this.endOfQueueAudioSource) {
          this.endOfQueueAudioSource.onended = null
        }
        this.endOfQueueAudioSource = source
        source.onended = () => {
          if (
            !this.audioQueue.length &&
            this.endOfQueueAudioSource === source
          ) {
            this.endOfQueueAudioSource = null
            console.log('🎵 [STREAMER] Fim da fila alcançado')
            if (this.isStreamComplete) {
              this.onComplete()
            }
          }
        }
      }

      source.buffer = audioBuffer
      source.connect(this.gainNode)

      // Garantir que nunca agendamos no passado
      const startTime = Math.max(this.scheduledTime, this.context.currentTime)
      source.start(startTime)
      this.scheduledTime = startTime + audioBuffer.duration

      console.log(`🎵 [STREAMER] Buffer agendado: start=${startTime.toFixed(3)}, duration=${audioBuffer.duration.toFixed(3)}`)
    }

    if (this.audioQueue.length === 0) {
      if (this.isStreamComplete) {
        console.log('🎵 [STREAMER] Stream completo, parando reprodução')
        this.isPlaying = false
        if (this.checkInterval) {
          clearInterval(this.checkInterval)
          this.checkInterval = null
        }
      } else {
        // Configurar verificação periódica para novos chunks
        if (!this.checkInterval) {
          this.checkInterval = window.setInterval(() => {
            if (this.audioQueue.length > 0) {
              this.scheduleNextBuffer()
            }
          }, 100) as unknown as number
        }
      }
    } else {
      // Agendar próxima verificação
      const nextCheckTime = (this.scheduledTime - this.context.currentTime) * 1000
      setTimeout(
        () => this.scheduleNextBuffer(),
        Math.max(0, nextCheckTime - 50)
      )
    }
  }

  stop() {
    console.log('🎵 [STREAMER] Parando reprodução')
    this.isPlaying = false
    this.isStreamComplete = true
    this.audioQueue = []
    this.scheduledTime = this.context.currentTime

    if (this.checkInterval) {
      clearInterval(this.checkInterval)
      this.checkInterval = null
    }

    this.gainNode.gain.linearRampToValueAtTime(
      0,
      this.context.currentTime + 0.1
    )

    setTimeout(() => {
      this.gainNode.disconnect()
      this.gainNode = this.context.createGain()
      this.gainNode.connect(this.context.destination)
    }, 200)
  }

  async resume() {
    console.log('🎵 [STREAMER] Resumindo reprodução')
    if (this.context.state === 'suspended') {
      await this.context.resume()
    }
    this.isStreamComplete = false
    this.scheduledTime = this.context.currentTime + this.initialBufferTime
    this.gainNode.gain.setValueAtTime(1, this.context.currentTime)
  }

  complete() {
    console.log('🎵 [STREAMER] Marcando stream como completo')
    this.isStreamComplete = true
    // Se não há mais buffers na fila, chama onComplete imediatamente
    if (this.audioQueue.length === 0) {
      this.onComplete()
    }
  }

  setVolume(volume: number) {
    const clampedVolume = Math.max(0, Math.min(1, volume))
    this.gainNode.gain.setValueAtTime(clampedVolume, this.context.currentTime)
  }

  getQueueLength(): number {
    return this.audioQueue.length
  }

  getIsPlaying(): boolean {
    return this.isPlaying
  }
}

export function useAudioStreamer(audioContext: AudioContext) {
  let streamer: AudioStreamer | null = null

  const createStreamer = () => {
    if (streamer) {
      streamer.stop()
    }
    streamer = new AudioStreamer(audioContext)
    return streamer
  }

  const getStreamer = () => {
    if (!streamer) {
      streamer = createStreamer()
    }
    return streamer
  }

  const destroy = () => {
    if (streamer) {
      streamer.stop()
      streamer = null
    }
  }

  return {
    createStreamer,
    getStreamer,
    destroy
  }
} 