/**
 * Audio utilities for generating test audio data
 */

export interface WAVGeneratorOptions {
  sampleRate?: number
  channels?: number
  bitsPerSample?: number
  frequency?: number
  duration?: number
  amplitude?: number
  waveType?: 'sine' | 'square' | 'sawtooth' | 'noise'
}

/**
 * Generate a valid WAV file as ArrayBuffer for testing audio playback
 */
export function generateTestWAV(options: WAVGeneratorOptions = {}): ArrayBuffer {
  const {
    sampleRate = 44100,
    channels = 1,
    bitsPerSample = 16,
    frequency = 440,
    duration = 1.0,
    amplitude = 0.1,
    waveType = 'sine'
  } = options

  const numSamples = Math.floor(sampleRate * duration)
  const dataLength = numSamples * channels * (bitsPerSample / 8)
  const bufferLength = 44 + dataLength // WAV header (44 bytes) + data

  const buffer = new ArrayBuffer(bufferLength)
  const view = new DataView(buffer)
  
  // WAV Header
  let offset = 0
  
  // RIFF chunk descriptor
  writeString(view, offset, 'RIFF'); offset += 4
  view.setUint32(offset, bufferLength - 8, true); offset += 4  // File size - 8
  writeString(view, offset, 'WAVE'); offset += 4
  
  // fmt sub-chunk
  writeString(view, offset, 'fmt '); offset += 4
  view.setUint32(offset, 16, true); offset += 4  // Subchunk1Size (16 for PCM)
  view.setUint16(offset, 1, true); offset += 2   // AudioFormat (1 for PCM)
  view.setUint16(offset, channels, true); offset += 2
  view.setUint32(offset, sampleRate, true); offset += 4
  view.setUint32(offset, sampleRate * channels * (bitsPerSample / 8), true); offset += 4  // ByteRate
  view.setUint16(offset, channels * (bitsPerSample / 8), true); offset += 2  // BlockAlign
  view.setUint16(offset, bitsPerSample, true); offset += 2
  
  // data sub-chunk
  writeString(view, offset, 'data'); offset += 4
  view.setUint32(offset, dataLength, true); offset += 4
  
  // Generate audio data
  for (let i = 0; i < numSamples; i++) {
    const t = i / sampleRate
    let sample = 0
    
    switch (waveType) {
      case 'sine':
        sample = Math.sin(2 * Math.PI * frequency * t)
        break
      case 'square':
        sample = Math.sin(2 * Math.PI * frequency * t) > 0 ? 1 : -1
        break
      case 'sawtooth':
        sample = 2 * ((frequency * t) % 1) - 1
        break
      case 'noise':
        sample = Math.random() * 2 - 1
        break
    }
    
    sample *= amplitude
    
    // Convert to 16-bit integer
    const intSample = Math.max(-32768, Math.min(32767, Math.floor(sample * 32767)))
    
    for (let channel = 0; channel < channels; channel++) {
      view.setInt16(offset, intSample, true)
      offset += 2
    }
  }
  
  return buffer
}

/**
 * Generate a sequence of test tones with different frequencies
 */
export function generateTestChord(frequencies: number[], duration = 0.5): ArrayBuffer[] {
  return frequencies.map(freq => generateTestWAV({
    frequency: freq,
    duration,
    amplitude: 0.08 // Lower amplitude for chords
  }))
}

/**
 * Generate a simple beep sound for notifications
 */
export function generateBeep(frequency = 800, duration = 0.2): ArrayBuffer {
  return generateTestWAV({
    frequency,
    duration,
    amplitude: 0.1,
    waveType: 'sine'
  })
}

/**
 * Generate a success sound (ascending tones)
 */
export function generateSuccessSound(): ArrayBuffer[] {
  const frequencies = [523, 659, 784] // C, E, G
  return generateTestChord(frequencies, 0.3)
}

/**
 * Generate an error sound (descending tones)
 */
export function generateErrorSound(): ArrayBuffer[] {
  const frequencies = [880, 659, 440] // A, E, A (lower)
  return generateTestChord(frequencies, 0.4)
}

/**
 * Validate if ArrayBuffer contains valid audio data
 */
export function validateAudioData(data: ArrayBuffer): boolean {
  if (!data || data.byteLength === 0) {
    return false
  }
  
  // Check for basic WAV header
  const view = new DataView(data)
  if (data.byteLength < 44) {
    return false
  }
  
  // Check RIFF signature
  const riff = getString(view, 0, 4)
  const wave = getString(view, 8, 4)
  
  return riff === 'RIFF' && wave === 'WAVE'
}

/**
 * Get audio metadata from WAV file
 */
export function getAudioMetadata(data: ArrayBuffer): {
  format: string
  sampleRate: number
  channels: number
  bitsPerSample: number
  duration: number
  fileSize: number
} | null {
  if (!validateAudioData(data)) {
    return null
  }
  
  const view = new DataView(data)
  
  const sampleRate = view.getUint32(24, true)
  const channels = view.getUint16(22, true)
  const bitsPerSample = view.getUint16(34, true)
  const dataSize = view.getUint32(40, true)
  
  const bytesPerSample = bitsPerSample / 8
  const numSamples = dataSize / (channels * bytesPerSample)
  const duration = numSamples / sampleRate
  
  return {
    format: 'WAV',
    sampleRate,
    channels,
    bitsPerSample,
    duration,
    fileSize: data.byteLength
  }
}

// Helper functions
function writeString(view: DataView, offset: number, string: string): void {
  for (let i = 0; i < string.length; i++) {
    view.setUint8(offset + i, string.charCodeAt(i))
  }
}

function getString(view: DataView, offset: number, length: number): string {
  let result = ''
  for (let i = 0; i < length; i++) {
    result += String.fromCharCode(view.getUint8(offset + i))
  }
  return result
} 